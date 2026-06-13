"""Agent artifact cache, served LAN-only to enrolling workstations.

Two kinds of artifacts:
- URL-backed: downloaded once from a pinned upstream URL, then cached.
- Prebuilt:   produced by scripts/build_agent_artifacts.sh on the server
  host and pre-placed in ARTIFACT_CACHE_DIR (wheels need a manylinux build
  env; the web dist is extracted from the linuxserver image). Never
  downloaded here.
"""
import asyncio
from pathlib import Path

import httpx

from app.config import Settings

_settings = Settings()
_lock = asyncio.Lock()

# name -> upstream URL (None = prebuilt, must be pre-placed)
ARTIFACTS: dict[str, str | None] = {
    "selkies-app.tar.gz": _settings.SELKIES_APP_URL,
    "wheelhouse-x86_64.tar.gz": None,
    "selkies-web.tar.gz": None,
    "libshim-x86_64.tar.gz": None,
    # nwg-drawer (app grid) + nwg-dock binaries — built on the server because
    # they are absent from some distro repos (e.g. Ubuntu 24.04).
    "nwg-shell-x86_64.tar.gz": None,
}


class ArtifactMissing(Exception):
    pass


async def _download(url: str, dest: Path) -> None:
    async with httpx.AsyncClient(timeout=600, follow_redirects=True) as client:
        async with client.stream("GET", url) as resp:
            resp.raise_for_status()
            with open(dest, "wb") as f:
                async for chunk in resp.aiter_bytes():
                    f.write(chunk)


async def ensure_artifact(name: str) -> Path:
    if name not in ARTIFACTS:
        raise ArtifactMissing(f"Unknown artifact: {name!r}")
    dest = Path(_settings.ARTIFACT_CACHE_DIR) / name
    if dest.is_file() and dest.stat().st_size > 0:
        return dest
    url = ARTIFACTS[name]
    if url is None:
        raise ArtifactMissing(
            f"{name} not found in {_settings.ARTIFACT_CACHE_DIR}. Run "
            "scripts/build_agent_artifacts.sh on the server host to build it.")
    async with _lock:
        if dest.is_file() and dest.stat().st_size > 0:  # re-check under lock
            return dest
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(".part")
        try:
            await _download(url, tmp)
            tmp.rename(dest)
        finally:
            tmp.unlink(missing_ok=True)
    return dest
