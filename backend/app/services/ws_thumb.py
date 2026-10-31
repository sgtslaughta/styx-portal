"""Workstation thumbnail files: {SCREENSHOT_CACHE_DIR}/ws-{id}.jpg, atomic writes."""
import os
from pathlib import Path

from app.config import Settings

_settings = Settings()
MAX_BYTES = 512 * 1024


def path(ws_id: str) -> Path:
    return Path(_settings.SCREENSHOT_CACHE_DIR) / f"ws-{ws_id}.jpg"


def write(ws_id: str, data: bytes) -> None:
    p = path(ws_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, p)


def delete(ws_id: str) -> None:
    path(ws_id).unlink(missing_ok=True)
