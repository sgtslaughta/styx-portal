"""Helpers for physical-workstation enrollment and lifecycle."""
import hashlib
import logging
import re
import socket
from datetime import datetime, timedelta, timezone

from sqlmodel import select

from app.config import Settings
from app.models import Workstation

_settings = Settings()

ENROLL_SCRIPT_PATH = "/api/enroll/script"
SELKIES_USER = "styx"


def sha256_hex(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def detect_lan_ip() -> str | None:
    """Best-effort local IP via the UDP routing trick (no packet is sent).

    On a host-network or bare-metal deployment this is the host's LAN IP.
    Inside a bridge-network container it yields the container IP, which is
    not reachable from the LAN — set SERVER_LAN_URL to override in that case.
    """
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
        finally:
            s.close()
    except OSError:
        return None
    return None if ip.startswith("127.") else ip


def lan_enroll_url() -> tuple[str | None, str]:
    """Return (base_url, source) for LAN enrollment.

    source: "env" (SERVER_LAN_URL set), "detected" (auto-detected IP),
    or "none" (no LAN URL available — public command only).
    """
    if _settings.SERVER_LAN_URL:
        return _settings.SERVER_LAN_URL.rstrip("/"), "env"
    ip = detect_lan_ip()
    if ip:
        # https in both modes: direct = Let's Encrypt on :443, tunnel = the
        # auto-generated self-signed LAN cert on websecure (pinned in command)
        return f"https://{ip}", "detected"
    return None, "none"


def lan_ca_pin(lan_base: str) -> tuple[str | None, bool]:
    """Return (pin, cert_created) for the LAN enrollment command.

    SERVER_CA_PIN wins when set. Otherwise, for hosts that a public cert
    cannot cover (any host in tunnel mode, IP addresses in direct mode),
    ensure the self-signed LAN cert exists and pin its fingerprint. Pin is
    None when the host is presumed covered by a real cert (direct + DNS).
    Caller refreshes Traefik routes when cert_created is True so the new
    cert gets served.
    """
    import ipaddress
    from urllib.parse import urlparse

    if _settings.SERVER_CA_PIN:
        return _settings.SERVER_CA_PIN, False
    if not lan_base.startswith("https://"):
        return None, False
    host = urlparse(lan_base).hostname or ""
    try:
        ipaddress.ip_address(host)
        is_ip = True
    except ValueError:
        is_ip = False
    if _settings.DEPLOY_MODE == "direct" and not is_ip:
        return None, False  # Let's Encrypt covers DNS names in direct mode
    from app.services.lan_tls import ensure_lan_cert
    try:
        _, fp, created = ensure_lan_cert([host])
    except OSError as e:
        logging.getLogger("styx-portal").error(
            "LAN cert generation failed (%s) — enroll command minted "
            "without --ca-pin", e)
        return None, False
    return f"sha256:{fp}", created


def build_enroll_command(raw_token: str, base: str,
                         ca_pin: str | None = None) -> str:
    cmd = (f"curl -fsSL {base}{ENROLL_SCRIPT_PATH} | bash -s -- "
           f"--token {raw_token} --server {base}")
    if ca_pin:
        cmd += f" --ca-pin {ca_pin}"
    return cmd


def slugify_hostname(hostname: str) -> str:
    s = re.sub(r"[^a-z0-9-]+", "-", hostname.lower()).strip("-")[:40]
    return s or "workstation"


async def unique_subdomain(session, hostname: str) -> str:
    base = slugify_hostname(hostname)
    candidate, n = base, 2
    while True:
        existing = await session.exec(
            select(Workstation).where(Workstation.subdomain == candidate))
        if existing.first() is None:
            return candidate
        candidate = f"{base}-{n}"
        n += 1


async def mark_stale_offline(session) -> bool:
    """Flip online workstations with stale heartbeats to offline.
    Returns True if anything changed (caller refreshes routes)."""
    cutoff = datetime.now(timezone.utc) - timedelta(
        seconds=_settings.WORKSTATION_OFFLINE_AFTER_S)
    result = await session.exec(
        select(Workstation).where(Workstation.status == "online"))
    changed = False
    for ws in result.all():
        hb = ws.last_heartbeat
        if hb is not None and hb.tzinfo is None:
            hb = hb.replace(tzinfo=timezone.utc)
        if hb is None or hb < cutoff:
            ws.status = "offline"
            session.add(ws)
            changed = True
    return changed
