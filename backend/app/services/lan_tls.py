"""Self-signed TLS for LAN access.

In tunnel mode (and for IP-address LAN URLs in direct mode) there is no
publicly-valid certificate for the portal's LAN address. This module
generates a persistent self-signed certificate (CA:TRUE so curl --cacert
and Python's cafile accept it directly) with the LAN host in its SAN, and
the enrollment one-liner pins its fingerprint — workstations get verified
TLS with zero manual cert work.

Traefik serves the cert via the shared lan-certs volume (route_writer emits
the defaultCertificate config). Regenerated only when the LAN host changes,
so pinned commands stay valid.
"""
import ipaddress
import json
import os
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from app.config import Settings

_settings = Settings()

CERT_NAME = "lan.crt"
KEY_NAME = "lan.key"
META_NAME = "lan.json"
VALID_DAYS = 3650


def cert_paths() -> tuple[Path, Path]:
    d = Path(_settings.LAN_CERT_DIR)
    return d / CERT_NAME, d / KEY_NAME


def cert_fingerprint(cert_path: Path) -> str:
    cert = x509.load_pem_x509_certificate(cert_path.read_bytes())
    return sha256(cert.public_bytes(serialization.Encoding.DER)).hexdigest()


def ensure_lan_cert(hosts: list[str]) -> tuple[Path, str, bool]:
    """Return (cert_path, sha256_fingerprint, created).

    Reuses the existing cert when it already covers all requested hosts —
    fingerprint stability keeps previously-minted pinned commands valid.
    """
    hosts = sorted({h for h in hosts if h})
    cert_path, key_path = cert_paths()
    meta_path = cert_path.parent / META_NAME
    if cert_path.is_file() and key_path.is_file() and meta_path.is_file():
        try:
            covered = set(json.loads(meta_path.read_text()).get("hosts", []))
            if set(hosts) <= covered:
                return cert_path, cert_fingerprint(cert_path), False
        except (json.JSONDecodeError, OSError, ValueError):
            pass  # unreadable/corrupt — regenerate below

    key = ec.generate_private_key(ec.SECP256R1())
    san: list[x509.GeneralName] = []
    for h in hosts:
        try:
            san.append(x509.IPAddress(ipaddress.ip_address(h)))
        except ValueError:
            san.append(x509.DNSName(h))
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "styx-portal-lan")])
    now = datetime.now(timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=VALID_DAYS))
        .add_extension(x509.SubjectAlternativeName(san), critical=False)
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(key, hashes.SHA256())
    )

    cert_path.parent.mkdir(parents=True, exist_ok=True)
    key_pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    fd = os.open(key_path, os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(key_pem)
    key_path.chmod(0o600)
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    meta_path.write_text(json.dumps({"hosts": hosts}))
    fp = sha256(cert.public_bytes(serialization.Encoding.DER)).hexdigest()
    return cert_path, fp, True
