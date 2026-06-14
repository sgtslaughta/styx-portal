import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlmodel import select, update
from sqlmodel.ext.asyncio.session import AsyncSession

from app.database import get_session
from app.models import User, Invite, RefreshToken, Instance, ServiceTemplate, FederatedIdentity
from app.schemas import UserOut, CreateInviteRequest, InviteOut, TempPasswordOut
from app.security.deps import require_admin
from app.security.passwords import hash_password, current_policy
from app.services.audit import audit_request

router = APIRouter()
INVITE_TTL_HOURS = 72


@router.get("", response_model=list[UserOut])
async def list_users(admin: User = Depends(require_admin),
                     session: AsyncSession = Depends(get_session)):
    result = await session.exec(select(User))
    return [_user_out(u) for u in result.all()]


@router.post("/invites", response_model=InviteOut, status_code=201)
async def create_invite(body: CreateInviteRequest, request: Request,
                        admin: User = Depends(require_admin),
                        session: AsyncSession = Depends(get_session)):
    if body.role not in ("admin", "user"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid role")
    raw = secrets.token_urlsafe(32)
    expires = datetime.now(timezone.utc) + timedelta(hours=INVITE_TTL_HOURS)
    session.add(Invite(
        token_hash=hashlib.sha256(raw.encode()).hexdigest(),
        email=body.email, role=body.role, created_by=admin.id, expires_at=expires,
    ))
    await audit_request(session, request, "invite.create", user_id=admin.id,
                        detail={"email": body.email, "role": body.role})
    await session.commit()
    return InviteOut(token=raw, expires_at=expires.isoformat())


@router.patch("/{user_id}/disable", response_model=UserOut)
async def disable_user(user_id: str, request: Request,
                       admin: User = Depends(require_admin),
                       session: AsyncSession = Depends(get_session)):
    user = await session.get(User, user_id)
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    if user.id == admin.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Cannot disable yourself")
    user.is_active = False
    session.add(user)
    await audit_request(session, request, "user.disable", user_id=admin.id,
                        resource=user.id)
    await session.commit()
    return _user_out(user)


@router.patch("/{user_id}/role", response_model=UserOut)
async def change_role(user_id: str, role: str, request: Request,
                      admin: User = Depends(require_admin),
                      session: AsyncSession = Depends(get_session)):
    if role not in ("admin", "user"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid role")
    user = await session.get(User, user_id)
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    if role == "user" and user.role == "admin":
        admins = (await session.exec(select(User).where(
            User.role == "admin", User.is_active == True))).all()  # noqa: E712
        if len(admins) <= 1:
            raise HTTPException(status.HTTP_400_BAD_REQUEST,
                                "cannot demote the last admin")
    user.role = role
    session.add(user)
    await audit_request(session, request, "user.role_change", user_id=admin.id,
                        resource=user.id, detail={"new_role": role, "via": "manual"})
    await session.commit()
    return _user_out(user)


@router.post("/{user_id}/unlock", response_model=UserOut)
async def unlock_user(user_id: str, request: Request,
                      admin: User = Depends(require_admin),
                      session: AsyncSession = Depends(get_session)):
    user = await session.get(User, user_id)
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    user.failed_count = 0
    user.locked_until = None
    session.add(user)
    await audit_request(session, request, "user.unlock", user_id=admin.id, resource=user.id)
    await session.commit()
    return _user_out(user)


def _user_out(u: User) -> UserOut:
    return UserOut(
        id=u.id, username=u.username, email=u.email, role=u.role,
        is_active=u.is_active,
        last_login=u.last_login.isoformat() if u.last_login else None,
        locked_until=u.locked_until.isoformat() if u.locked_until else None,
        failed_count=u.failed_count,
    )
