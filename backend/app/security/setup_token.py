"""One-time first-run setup code.

While no user exists, POST /api/auth/setup must present this code. It is
generated on demand, logged at boot and kept in <data dir>/setup-token (0600);
deleted once the first admin exists.
"""
import asyncio
import logging
import os
import secrets
from pathlib import Path

from app.config import Settings

logger = logging.getLogger("styx-portal")
_settings = Settings()

# Serialises first-run creation so racing requests cannot both create an admin.
setup_lock = asyncio.Lock()


def _path() -> Path:
    return Path(_settings.SECRETS_FILE).parent / "setup-token"


def current() -> str:
    """The active setup code, creating (0600) it if missing."""
    p = _path()
    try:
        tok = p.read_text().strip()
        if tok:
            return tok
    except FileNotFoundError:
        pass
    tok = secrets.token_urlsafe(24)
    p.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(tok)
    return tok


def verify(candidate: str | None) -> bool:
    return bool(candidate) and secrets.compare_digest(candidate.encode(), current().encode())


def clear() -> None:
    _path().unlink(missing_ok=True)


def announce(setup_pending: bool) -> None:
    """Boot hook: log the code while setup is pending, else drop a stale file."""
    if not setup_pending:
        clear()
        return
    logger.warning("Styx setup code: %s  (needed to create the first admin; also in %s)",
                   current(), _path())
