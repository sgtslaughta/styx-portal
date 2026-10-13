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


async def session_user_or_none(request: Request, session: AsyncSession) -> User | None:
    """Same checks as get_current_user, but None instead of 401 (forwardAuth use)."""
    try:
        return await get_current_user(request, session)
    except HTTPException:
        return None
