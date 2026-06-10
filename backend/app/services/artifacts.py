"""Selkies tarball download cache. Full implementation in Task 10."""
from pathlib import Path

from app.config import Settings

_settings = Settings()


async def ensure_selkies_tarball() -> Path:
    dest = Path(_settings.ARTIFACT_CACHE_DIR) / "selkies.tar.gz"
    if dest.is_file() and dest.stat().st_size > 0:
        return dest
    raise FileNotFoundError(dest)
