"""Helpers for physical-workstation enrollment and lifecycle."""
import hashlib
import re
from datetime import datetime, timedelta, timezone

from sqlmodel import select

from app.config import Settings
from app.models import Workstation

_settings = Settings()

ENROLL_SCRIPT_PATH = "/api/enroll/script"
SELKIES_USER = "styx"


def sha256_hex(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def build_enroll_command(raw_token: str) -> str:
    base = _settings.server_lan_url()
    cmd = (f"curl -fsSL {base}{ENROLL_SCRIPT_PATH} | bash -s -- "
           f"--token {raw_token} --server {base}")
    if _settings.SERVER_CA_PIN:
        cmd += f" --ca-pin {_settings.SERVER_CA_PIN}"
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
