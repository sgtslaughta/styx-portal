import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.database import get_session
from app.models import User, Invite
from app.schemas import UserOut, CreateInviteRequest, InviteOut
from app.security.deps import require_admin

router = APIRouter()
INVITE_TTL_HOURS = 72


@router.get("", response_model=list[UserOut])
async def list_users(admin: User = Depends(require_admin),
                     session: AsyncSession = Depends(get_session)):
    result = await session.exec(select(User))
    return [UserOut(id=u.id, username=u.username, email=u.email,
                    role=u.role, is_active=u.is_active) for u in result.all()]


@router.post("/invites", response_model=InviteOut, status_code=201)
async def create_invite(body: CreateInviteRequest, admin: User = Depends(require_admin),
                        session: AsyncSession = Depends(get_session)):
    if body.role not in ("admin", "user"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid role")
    raw = secrets.token_urlsafe(32)
    expires = datetime.now(timezone.utc) + timedelta(hours=INVITE_TTL_HOURS)
    session.add(Invite(
        token_hash=hashlib.sha256(raw.encode()).hexdigest(),
        email=body.email, role=body.role, created_by=admin.id, expires_at=expires,
    ))
    await session.commit()
    return InviteOut(token=raw, expires_at=expires.isoformat())


@router.patch("/{user_id}/disable", response_model=UserOut)
async def disable_user(user_id: str, admin: User = Depends(require_admin),
                       session: AsyncSession = Depends(get_session)):
    user = await session.get(User, user_id)
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    if user.id == admin.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Cannot disable yourself")
    user.is_active = False
    session.add(user)
    await session.commit()
    return UserOut(id=user.id, username=user.username, email=user.email,
                   role=user.role, is_active=user.is_active)


@router.patch("/{user_id}/role", response_model=UserOut)
async def change_role(user_id: str, role: str, admin: User = Depends(require_admin),
                      session: AsyncSession = Depends(get_session)):
    if role not in ("admin", "user"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid role")
    user = await session.get(User, user_id)
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    user.role = role
    session.add(user)
    await session.commit()
    return UserOut(id=user.id, username=user.username, email=user.email,
                   role=user.role, is_active=user.is_active)
