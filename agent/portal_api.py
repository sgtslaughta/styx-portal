"""Portal API client for the Styx agent, with TLS pinning."""
import json
import ssl
import urllib.request
from hashlib import sha256
from pathlib import Path


# --- TLS pinning -----------------------------------------------------------
# Enrollment verified the server certificate's SHA256 fingerprint against the
# pin embedded in the minted command and saved the cert to server_cert (PEM).
# We use that cert as the ONLY trusted CA — full chain verification against
# the pinned cert, never an unverified connection. Hostname check is off
# because self-signed LAN certs rarely carry the LAN IP in their SAN; trust
# comes from the pin, not the name.
def _ssl_context(cfg: dict) -> ssl.SSLContext:
    cert_file = cfg.get("server_cert", "")
    if cert_file and Path(cert_file).is_file():
        ctx = ssl.create_default_context(cafile=cert_file)
        ctx.check_hostname = False
        return ctx
    return ssl.create_default_context()


def check_pin(cert_file: str, ca_pin: str) -> bool:
    """Doctor check: pinned cert file still matches the fingerprint."""
    if not ca_pin or not cert_file:
        return True
    expected = ca_pin.split(":", 1)[1].replace(":", "").lower()
    pem = Path(cert_file).read_text()
    der = ssl.PEM_cert_to_DER_cert(pem)
    return sha256(der).hexdigest() == expected


def api(cfg: dict, path: str, payload: dict | None = None) -> dict:
    url = cfg["server"].rstrip("/") + path
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        url, data=data, method="POST" if data is not None else "GET",
        headers={"Authorization": f"Bearer {cfg['agent_token']}",
                 "Content-Type": "application/json"})
    ctx = _ssl_context(cfg) if url.startswith("https") else None
    with urllib.request.urlopen(req, timeout=15, context=ctx) as resp:
        return json.loads(resp.read().decode() or "{}")
