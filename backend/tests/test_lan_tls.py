import pytest
from cryptography import x509
from cryptography.x509.oid import ExtensionOID

from app.services import lan_tls


@pytest.fixture(autouse=True)
def _cert_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(lan_tls._settings, "LAN_CERT_DIR", str(tmp_path))
    return tmp_path


def _load(cert_path):
    return x509.load_pem_x509_certificate(cert_path.read_bytes())


def test_generates_cert_with_ip_and_dns_sans(_cert_dir):
    cert_path, fp, created = lan_tls.ensure_lan_cert(["192.168.1.10", "portal.local"])
    assert created is True
    assert cert_path.is_file()
    assert len(fp) == 64
    cert = _load(cert_path)
    san = cert.extensions.get_extension_for_oid(
        ExtensionOID.SUBJECT_ALTERNATIVE_NAME).value
    assert "portal.local" in san.get_values_for_type(x509.DNSName)
    assert [str(ip) for ip in san.get_values_for_type(x509.IPAddress)] == ["192.168.1.10"]
    bc = cert.extensions.get_extension_for_oid(ExtensionOID.BASIC_CONSTRAINTS).value
    assert bc.ca is True  # so curl --cacert / python cafile accept the self-signed leaf
    key_path = _cert_dir / "lan.key"
    assert oct(key_path.stat().st_mode)[-3:] == "600"


def test_reuses_existing_cert_for_same_hosts(_cert_dir):
    _, fp1, created1 = lan_tls.ensure_lan_cert(["192.168.1.10"])
    _, fp2, created2 = lan_tls.ensure_lan_cert(["192.168.1.10"])
    assert created1 is True and created2 is False
    assert fp1 == fp2  # stable fingerprint — pinned commands keep working


def test_regenerates_when_host_not_covered(_cert_dir):
    _, fp1, _ = lan_tls.ensure_lan_cert(["192.168.1.10"])
    _, fp2, created = lan_tls.ensure_lan_cert(["10.0.0.5"])
    assert created is True
    assert fp1 != fp2
