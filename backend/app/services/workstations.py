"""Helpers for physical-workstation enrollment and lifecycle."""
import hashlib
import logging
import re
import socket
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlmodel import select

from app.config import Settings
from app.models import Workstation
from app.services.settings_store import settings as _sys_settings

_settings = Settings()

ENROLL_SCRIPT_PATH = "/api/enroll/script"
SELKIES_USER = "styx"

_version_cache: dict[str, tuple[float, str]] = {}


def get_latest_agent_version(agent_dir: str | None = None) -> str:
    """The AGENT_VERSION of the styx_agent.py this server serves — the build a
    fresh enrollment would install. Cached per path+mtime. Empty when the file
    is missing/unparseable (callers then flag nothing as outdated)."""
    path = Path(agent_dir or _settings.AGENT_DIR) / "styx_agent.py"
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return ""
    cached = _version_cache.get(str(path))
    if cached and cached[0] == mtime:
        return cached[1]
    m = re.search(r'AGENT_VERSION\s*=\s*"([^"]+)"', path.read_text())
    version = m.group(1) if m else ""
    _version_cache[str(path)] = (mtime, version)
    return version


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


def lan_ca_pin(lan_base: str) -> tuple[str | None, str | None, bool]:
    """Return (cert_pin, pubkey_pin, cert_created) for the LAN command.

    - cert_pin (`sha256:<hex>`) is verified inside enroll.sh and pins the
      saved cert the agent later trusts.
    - pubkey_pin (`sha256//<b64>`) is curl's --pinnedpubkey value, letting
      the bootstrap script fetch verify the self-signed cert with no CA.

    SERVER_CA_PIN overrides cert_pin (no pubkey pin: operator manages TLS).
    Both are None when a public cert is presumed to cover the host (direct
    mode + DNS name). cert_created=True ⇒ caller refreshes Traefik routes.
    """
    import ipaddress
    from urllib.parse import urlparse

    if _settings.SERVER_CA_PIN:
        return _settings.SERVER_CA_PIN, None, False
    if not lan_base.startswith("https://"):
        return None, None, False
    host = urlparse(lan_base).hostname or ""
    try:
        ipaddress.ip_address(host)
        is_ip = True
    except ValueError:
        is_ip = False
    if _settings.DEPLOY_MODE == "direct" and not is_ip:
        return None, None, False  # Let's Encrypt covers DNS names in direct mode
    from app.services.lan_tls import cert_paths, cert_pubkey_pin, ensure_lan_cert
    try:
        _, fp, created = ensure_lan_cert([host])
        pubkey_pin = cert_pubkey_pin(cert_paths()[0])
    except OSError as e:
        logging.getLogger("styx-portal").error(
            "LAN cert generation failed (%s) — enroll command minted "
            "without TLS pin", e)
        return None, None, False
    return f"sha256:{fp}", pubkey_pin, created


def build_enroll_command(raw_token: str, base: str,
                         ca_pin: str | None = None,
                         pubkey_pin: str | None = None) -> str:
    # --pinnedpubkey pins the server's public key so the bootstrap fetch is
    # MITM-safe over self-signed TLS; -k only skips CA-chain validation (the
    # cert is a self-signed root) — identity is still cryptographically
    # enforced by the pin. The script then re-verifies via --ca-pin.
    head = "curl -fsSL"
    if pubkey_pin:
        head += f" --pinnedpubkey '{pubkey_pin}' -k"
    cmd = (f"{head} {base}{ENROLL_SCRIPT_PATH} | bash -s -- "
           f"--token {raw_token} --server {base}")
    if ca_pin:
        cmd += f" --ca-pin {ca_pin}"
    return cmd


# (remote endpoint name, local filename in the install dir)
AGENT_UPDATE_FILES = [
    ("agent.py", "styx_agent.py"),
    ("engine.py", "engine.py"),
    ("gateway.py", "gateway.py"),
    ("selkies_launcher.py", "selkies_launcher.py"),
    ("clipboard_bridge.py", "clipboard_bridge.py"),
]


def build_update_command(base: str, *, insecure: bool = False) -> str:
    """Copy-paste one-liner that re-pulls the agent python files from the public
    /api/enroll/* endpoints and restarts the user service. No enrollment token
    needed; the venv/wheels/artifacts are left untouched (code-only update)."""
    flag = "-fsSLk" if insecure else "-fsSL"
    pairs = " ".join(f"{remote}:{local}" for remote, local in AGENT_UPDATE_FILES)
    return (
        'INSTALL="$HOME/.local/share/styx-agent"; '
        f'for f in {pairs}; do '
        f'curl {flag} "{base}/api/enroll/${{f%%:*}}" -o "$INSTALL/${{f##*:}}"; '
        'done; '
        'systemctl --user restart styx-agent'
    )


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
        seconds=_sys_settings.get("WORKSTATION_OFFLINE_AFTER_S"))
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
