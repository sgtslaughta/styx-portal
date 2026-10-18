from fastapi import Depends, HTTPException, Request, status
from sqlmodel.ext.asyncio.session import AsyncSession

from app.database import get_session
from app.models import User
from app.security import tokens


# Everything else is refused while a temporary/forced password is still in place.
_PW_CHANGE_OK = frozenset({"/api/auth/me", "/api/auth/change-password", "/api/auth/logout"})


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
    if claims.get("tv", 0) != user.token_version:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token revoked")
    if user.must_change_pw and request.url.path not in _PW_CHANGE_OK:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Password change required")
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


async def proxy_user_or_none(request: Request, session: AsyncSession) -> User | None:
    """User behind a valid styx_proxy cookie, else None (forwardAuth only).

    Valid = signature + exp, type "proxy", its refresh family still has a live
    (unrevoked, unexpired) row for the same user, and the user is active. API
    tokens are never accepted here; the proxy token is never accepted by the API.
    """
    from datetime import datetime, timezone
    from sqlmodel import select
    from app.models import RefreshToken
    from app.security.cookies import PROXY_COOKIE
    raw = request.cookies.get(PROXY_COOKIE)
    if not raw:
        return None
    try:
        claims = tokens.decode_token(raw)
    except tokens.TokenError:
        return None
    if claims.get("type") != "proxy" or not claims.get("fam"):
        return None
    rows = (await session.exec(select(RefreshToken).where(
        RefreshToken.family_id == claims["fam"],
        RefreshToken.user_id == claims.get("sub"),
        RefreshToken.revoked == False))).all()  # noqa: E712
    now = datetime.now(timezone.utc)
    if not any((r.expires_at if r.expires_at.tzinfo else
                r.expires_at.replace(tzinfo=timezone.utc)) > now for r in rows):
        return None
    user = await session.get(User, claims["sub"])
    if not user or not user.is_active:
        return None
    # Same revocation rules as the API: password/role/disable bump token_version, and a
    # forced password change blocks apps and streams until it is done.
    if claims.get("tv", 0) != user.token_version or user.must_change_pw:
        return None
    return user
