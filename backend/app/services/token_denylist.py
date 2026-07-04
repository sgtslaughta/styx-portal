"""Access-token jti denylist for hard kill-on-logout.

Access tokens are stateless and stay valid until exp; logout clears the cookie
but can't invalidate the token value. This denylist lets logout revoke a token
immediately — closing the replay window (notably the workstation stream
reconnect after logout). Entries only need to live until the token's own exp,
so they are purged opportunistically on write.
"""
from datetime import datetime, timezone

from sqlmodel import delete
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import RevokedAccessToken


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def revoke_access(session: AsyncSession, jti: str, expires_at: datetime) -> None:
    """Add an access-token jti to the denylist (caller commits). Also purges
    entries already past their exp — a revoked token is dead by then anyway."""
    if not jti:
        return
    await session.exec(delete(RevokedAccessToken).where(
        RevokedAccessToken.expires_at < _now()))
    if await session.get(RevokedAccessToken, jti) is None:
        session.add(RevokedAccessToken(jti=jti, expires_at=expires_at))


async def is_access_revoked(session: AsyncSession, jti: str | None) -> bool:
    """True if this access-token jti has been revoked. Presence is revocation:
    expired entries are purged on write, and an expired token is rejected by
    decode_token before this is ever consulted — so no exp comparison here
    (which would also trip on SQLite's tz-naive datetimes)."""
    if not jti:
        return False
    return await session.get(RevokedAccessToken, jti) is not None
