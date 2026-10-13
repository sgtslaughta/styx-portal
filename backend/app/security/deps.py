from fastapi import Depends, HTTPException, Request, status
from sqlmodel.ext.asyncio.session import AsyncSession

from app.database import get_session
from app.models import User
from app.security import tokens


async def get_current_user(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> User:
    raw = request.cookies.get("access_token")
    if not raw:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    try:
        claims = tokens.decode_token(raw)
    except tokens.TokenError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token")
    if claims.get("type") != "access":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Wrong token type")
    from app.services import token_denylist
    if await token_denylist.is_access_revoked(session, claims.get("jti")):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token revoked")
    user = await session.get(User, claims["sub"])
    if not user or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User inactive")
    return user


async def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin required")
    return user


def require_owner_or_admin(owner_id: str | None, user: User) -> None:
    if user.role == "admin":
        return
    if owner_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not the owner")


async def refresh_user_or_none(request: Request, session: AsyncSession) -> User | None:
    """User behind a valid, unrevoked refresh_token cookie, else None. Read-only.

    Same validation as POST /api/auth/refresh (signature, exp, type, stored row
    not revoked, active user) but never rotates: forwardAuth cannot set cookies.
    Reuse detection (family kill) stays in /refresh, where rotation happens.
    """
    from app.models import RefreshToken
    raw = request.cookies.get("refresh_token")
    if not raw:
        return None
    try:
        claims = tokens.decode_token(raw)
    except tokens.TokenError:
        return None
    if claims.get("type") != "refresh":
        return None
    stored = await session.get(RefreshToken, claims.get("jti"))
    if not stored or stored.revoked or stored.user_id != claims.get("sub"):
        return None
    user = await session.get(User, claims["sub"])
    return user if user and user.is_active else None


async def session_user_or_none(request: Request, session: AsyncSession) -> User | None:
    """get_current_user, else a valid refresh token; None instead of 401 (forwardAuth).

    Path-mode apps never call /api/auth/refresh, so without the fallback every
    service would bounce to /login when the 15-min access token expires.
    """
    try:
        return await get_current_user(request, session)
    except HTTPException:
        return await refresh_user_or_none(request, session)
