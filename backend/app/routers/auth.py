import hashlib
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlmodel import select, update
from sqlmodel.ext.asyncio.session import AsyncSession

from app.config import Settings
from app.database import get_session
from app.models import User, Invite, RefreshToken, Instance, ServiceTemplate
from app.schemas import SetupRequest, LoginRequest, AcceptInviteRequest, UserOut
from app.security import tokens
from app.security.passwords import hash_password, verify_password
from app.security.csrf import new_csrf_token, CSRF_COOKIE
from app.security.deps import get_current_user
from app.security.setup_gate import users_exist

router = APIRouter()
_settings = Settings()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def _set_auth_cookies(resp: Response, access: str, refresh: str, csrf: str) -> None:
    common = dict(
        httponly=True,
        secure=_settings.COOKIE_SECURE,
        samesite="strict",
        domain=_settings.COOKIE_DOMAIN,
    )
    resp.set_cookie("access_token", access, max_age=_settings.ACCESS_TTL, **common)
    resp.set_cookie("refresh_token", refresh, max_age=_settings.REFRESH_TTL, **common)
    resp.set_cookie(
        CSRF_COOKIE, csrf, max_age=_settings.REFRESH_TTL,
        httponly=False, secure=_settings.COOKIE_SECURE,
        samesite="strict", domain=_settings.COOKIE_DOMAIN,
    )


def _clear_auth_cookies(resp: Response) -> None:
    for name in ("access_token", "refresh_token", CSRF_COOKIE):
        resp.delete_cookie(name, domain=_settings.COOKIE_DOMAIN)


async def _issue_session(resp: Response, session: AsyncSession, user: User, request: Request) -> None:
    access = tokens.create_access_token(user.id, user.role)
    refresh, jti = tokens.create_refresh_token(user.id)
    session.add(RefreshToken(
        jti=jti, user_id=user.id,
        expires_at=_now() + timedelta(seconds=_settings.REFRESH_TTL),
        user_agent=request.headers.get("user-agent"),
    ))
    user.last_login = _now()
    session.add(user)
    await session.commit()
    _set_auth_cookies(resp, access, refresh, new_csrf_token())


@router.get("/setup-required")
async def setup_required(session: AsyncSession = Depends(get_session)):
    return {"setup_required": not await users_exist(session)}


@router.post("/setup", response_model=UserOut, status_code=201)
async def setup(body: SetupRequest, request: Request, response: Response,
                session: AsyncSession = Depends(get_session)):
    if await users_exist(session):
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    user = User(username=body.username, email=body.email,
                password_hash=hash_password(body.password), role="admin")
    session.add(user)
    await session.flush()
    await session.exec(update(Instance).where(Instance.owner_id == None).values(owner_id=user.id))  # noqa: E711
    await session.exec(update(ServiceTemplate).where(ServiceTemplate.owner_id == None).values(owner_id=user.id))  # noqa: E711
    await _issue_session(response, session, user, request)
    return UserOut(id=user.id, username=user.username, email=user.email,
                   role=user.role, is_active=user.is_active)


@router.post("/login")
async def login(body: LoginRequest, request: Request, response: Response,
                session: AsyncSession = Depends(get_session)):
    result = await session.exec(select(User).where(User.username == body.username))
    user = result.first()
    if not user or not user.is_active or not verify_password(body.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")
    await _issue_session(response, session, user, request)
    return {"id": user.id, "username": user.username, "role": user.role,
            "must_change_pw": user.must_change_pw}


@router.post("/refresh")
async def refresh(request: Request, response: Response,
                  session: AsyncSession = Depends(get_session)):
    raw = request.cookies.get("refresh_token")
    if not raw:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "No refresh token")
    try:
        claims = tokens.decode_token(raw)
    except tokens.TokenError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid refresh token")
    if claims.get("type") != "refresh":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Wrong token type")
    stored = await session.get(RefreshToken, claims["jti"])
    if not stored or stored.revoked:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Refresh revoked")
    user = await session.get(User, claims["sub"])
    if not user or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User inactive")
    stored.revoked = True
    session.add(stored)
    await _issue_session(response, session, user, request)
    return {"ok": True}


@router.post("/logout")
async def logout(request: Request, response: Response,
                 session: AsyncSession = Depends(get_session)):
    raw = request.cookies.get("refresh_token")
    if raw:
        try:
            claims = tokens.decode_token(raw)
            stored = await session.get(RefreshToken, claims.get("jti"))
            if stored:
                stored.revoked = True
                session.add(stored)
                await session.commit()
        except tokens.TokenError:
            pass
    _clear_auth_cookies(response)
    return {"ok": True}


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(get_current_user)):
    return UserOut(id=user.id, username=user.username, email=user.email,
                   role=user.role, is_active=user.is_active)


@router.post("/accept-invite", status_code=201)
async def accept_invite(body: AcceptInviteRequest, request: Request, response: Response,
                        session: AsyncSession = Depends(get_session)):
    result = await session.exec(select(Invite).where(Invite.token_hash == _hash_token(body.token)))
    inv = result.first()
    if not inv or inv.used_at is not None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid or used invite")
    if inv.expires_at and inv.expires_at < _now():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invite expired")
    exists = await session.exec(select(User).where(User.username == body.username))
    if exists.first():
        raise HTTPException(status.HTTP_409_CONFLICT, "Username taken")
    user = User(username=body.username, email=inv.email,
                password_hash=hash_password(body.password), role=inv.role)
    inv.used_at = _now()
    session.add_all([user, inv])
    await _issue_session(response, session, user, request)
    return {"id": user.id, "username": user.username, "role": user.role}
