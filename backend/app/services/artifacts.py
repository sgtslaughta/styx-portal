"""Selkies tarball download cache.

The enrollment script fetches the Selkies portable tarball from this server,
not from the internet — workstations only need LAN reachability. The file is
downloaded once from SELKIES_TARBALL_URL and cached. Pre-placing the file at
{ARTIFACT_CACHE_DIR}/selkies.tar.gz also works (air-gapped installs).
"""
import asyncio
from pathlib import Path

import httpx

from app.config import Settings

_settings = Settings()
_lock = asyncio.Lock()


async def _download(url: str, dest: Path) -> None:
    async with httpx.AsyncClient(timeout=600, follow_redirects=True) as client:
        async with client.stream("GET", url) as resp:
            resp.raise_for_status()
            with open(dest, "wb") as f:
                async for chunk in resp.aiter_bytes():
                    f.write(chunk)


async def ensure_selkies_tarball() -> Path:
    dest = Path(_settings.ARTIFACT_CACHE_DIR) / "selkies.tar.gz"
    if dest.is_file() and dest.stat().st_size > 0:
        return dest
    async with _lock:
        if dest.is_file() and dest.stat().st_size > 0:  # re-check under lock
            return dest
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(".part")
        try:
            await _download(_settings.SELKIES_TARBALL_URL, tmp)
            tmp.rename(dest)
        finally:
            tmp.unlink(missing_ok=True)
    return dest
