"""Workstation favicon cache: <install>/favicon (+ .type, .etag), written
atomically, fetched from the portal when the heartbeat's icon_etag changes."""
import os
from pathlib import Path

from portal_api import api_bytes

MAX_BYTES = 512 * 1024
TYPES = {"image/png", "image/svg+xml", "image/x-icon", "image/webp"}


def _put(path: Path, data: bytes) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def cached_etag(install: Path) -> str:
    try:
        return (install / "favicon.etag").read_text().strip()
    except OSError:
        return ""


def read(install: Path) -> tuple[bytes, str, str] | None:
    """(body, content type, etag) or None when nothing is cached."""
    try:
        return ((install / "favicon").read_bytes(),
                (install / "favicon.type").read_text().strip(),
                cached_etag(install))
    except OSError:
        return None


def sync(cfg: dict, install: Path, etag: str, fetch=api_bytes) -> bool:
    """Fetch + cache the icon when `etag` (from the heartbeat) is new.
    Never raises: failures are logged and retried on the next heartbeat.
    The etag stored is the one the fetch returned, so an icon changed between
    heartbeat and fetch is not mistaken for stale."""
    if not etag or etag == cached_etag(install):
        return False
    try:
        body, ctype, got = fetch(cfg, "/api/agent/icon")
        if ctype not in TYPES or not body or len(body) > MAX_BYTES:
            raise ValueError(f"unusable icon response ({ctype}, {len(body)} bytes)")
        install.mkdir(parents=True, exist_ok=True)
        _put(install / "favicon.type", ctype.encode())   # type first: a crash between the writes leaves new type + old bytes (harmless under nosniff + CSP; next sync fixes)
        _put(install / "favicon", body)
        _put(install / "favicon.etag", (got or etag).encode())   # last: marks complete
        return True
    except Exception as e:  # noqa: BLE001 - supervisor must survive any icon fault
        print(f"favicon sync failed: {e}", flush=True)
        return False


def on_heartbeat(cfg: dict, hb: dict) -> bool:
    """Supervisor hook: sync into the same install dir the gateway reads."""
    return sync(cfg, Path(cfg["install_dir"]), hb.get("icon_etag", ""))
