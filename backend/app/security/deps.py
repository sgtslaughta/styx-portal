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
