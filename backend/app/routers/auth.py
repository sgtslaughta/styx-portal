import asyncio
import hashlib
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse
from sqlmodel import select, update
from sqlmodel.ext.asyncio.session import AsyncSession

from app.config import Settings
from app.database import get_session
from app.models import User, Invite, RefreshToken, Instance, ServiceTemplate, OAuthProvider, FederatedIdentity, Workstation
from app.schemas import SetupRequest, LoginRequest, AcceptInviteRequest, UserOut, ConnectedIdentity, ChangePasswordRequest
from app.security import tokens, oauth
from app.security.passwords import hash_password, verify_password, validate_password, current_policy
from app.security.csrf import new_csrf_token, CSRF_COOKIE
from app.security.deps import get_current_user
from app.security.setup_gate import users_exist
from app.services import federation
from app.services.audit import audit_request
from app.middleware.rate_limit import client_ip_from_headers
from app.services.abuse import fail_tracker, ban_cache, ban_ip
from app.services.settings_store import settings as sys_settings

router = APIRouter()
_settings = Settings()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt: datetime) -> datetime:
    """Treat a naive datetime (as SQLite returns) as UTC for comparison."""
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


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


async def _issue_session(resp: Response, session: AsyncSession, user: User, request: Request,
                         family_id: str | None = None) -> None:
    access = tokens.create_access_token(user.id, user.role)
    refresh, jti = tokens.create_refresh_token(user.id)
    session.add(RefreshToken(
        jti=jti, user_id=user.id,
        family_id=family_id or jti,
        expires_at=_now() + timedelta(seconds=sys_settings.get("REFRESH_TTL")),
        user_agent=request.headers.get("user-agent"),
    ))
    user.last_login = _now()
    session.add(user)
    await session.commit()
    _set_auth_cookies(resp, access, refresh, new_csrf_token())


@router.get("/csrf")
async def csrf_bootstrap(response: Response):
    """Issue an anonymous CSRF cookie so pre-auth POSTs (accept-invite) can
    pass the double-submit check."""
    response.set_cookie(
        CSRF_COOKIE, new_csrf_token(), max_age=600,
        httponly=False, secure=_settings.COOKIE_SECURE,
        samesite="strict", domain=_settings.COOKIE_DOMAIN,
    )
    return {"ok": True}


@router.get("/setup-required")
async def setup_required(session: AsyncSession = Depends(get_session)):
    return {"setup_required": not await users_exist(session)}


@router.get("/setup-preflight")
async def setup_preflight(session: AsyncSession = Depends(get_session)):
    # Only meaningful during genuine first-run; hide once an admin exists so infra
    # status is never exposed post-setup without auth.
    if await users_exist(session):
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    from app.services.docker_manager import DockerManager
    docker = DockerManager(network_name=_settings.DOCKER_NETWORK)
    reachable = await asyncio.to_thread(docker.ping)
    data_dir = Path(_settings.SCREENSHOT_CACHE_DIR).parent  # /app/data
    try:
        probe = data_dir / ".preflight"
        probe.write_text("x")
        probe.unlink()
        writable = True
    except Exception:  # noqa: BLE001
        writable = False
    return {
        "docker": {
            "ok": reachable,
            "detail": "reachable" if reachable else "not reachable — is docker-proxy running?",
        },
        "deploy_mode": _settings.DEPLOY_MODE,
        "domain_set": bool(_settings.DOMAIN) and _settings.DOMAIN != "localhost",
        "data_writable": writable,
    }


@router.post("/setup", response_model=UserOut, status_code=201)
async def setup(body: SetupRequest, request: Request, response: Response,
                session: AsyncSession = Depends(get_session)):
    if await users_exist(session):
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    try:
        validate_password(body.password, current_policy())
    except ValueError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e))
    user = User(username=body.username, email=body.email,
                password_hash=hash_password(body.password), role="admin")
    session.add(user)
    await session.flush()
    await session.exec(update(Instance).where(Instance.owner_id == None).values(owner_id=user.id))  # noqa: E711
    await session.exec(update(ServiceTemplate).where(ServiceTemplate.owner_id == None).values(owner_id=user.id))  # noqa: E711
    await _issue_session(response, session, user, request)
    await audit_request(session, request, "auth.signup", user_id=user.id,
                        detail={"role": user.role, "via": "setup"})
    await session.commit()
    return UserOut(id=user.id, username=user.username, email=user.email,
                   role=user.role, is_active=user.is_active)


@router.post("/login")
async def login(body: LoginRequest, request: Request, response: Response,
                session: AsyncSession = Depends(get_session)):
    ip = client_ip_from_headers(request)
    result = await session.exec(select(User).where(User.username == body.username))
    user = result.first()

    # Per-username lockout: refuse before checking the password.
    if user and user.locked_until and _aware(user.locked_until) > _now():
        await audit_request(session, request, "auth.login_locked", user_id=user.id)
        await session.commit()
        retry = int((_aware(user.locked_until) - _now()).total_seconds())
        raise HTTPException(
            status.HTTP_423_LOCKED, "Account temporarily locked",
            headers={"Retry-After": str(max(retry, 1))},
        )

    if not user or not user.is_active or not verify_password(body.password, user.password_hash):
        if user:
            user.failed_count += 1
            if user.failed_count >= sys_settings.get("LOCKOUT_THRESHOLD"):
                user.locked_until = _now() + timedelta(seconds=sys_settings.get("LOCKOUT_DURATION"))
                user.failed_count = 0
            session.add(user)
        # Per-IP abuse detector -> proxy ban (L3). Thresholds are live-tunable.
        fail_tracker.threshold = sys_settings.get("BAN_FAIL_THRESHOLD")
        fail_tracker.window = sys_settings.get("BAN_FAIL_WINDOW")
        if fail_tracker.record(ip):
            await ban_ip(session, ip, "brute-force: failed logins",
                         sys_settings.get("BAN_DURATION"))
            ban_cache.invalidate()
        await audit_request(session, request, "auth.login_failed",
                            detail={"username": body.username})
        await session.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")

    # Success: clear lockout state.
    user.failed_count = 0
    user.locked_until = None
    session.add(user)
    await _issue_session(response, session, user, request)
    await audit_request(session, request, "auth.login", user_id=user.id)
    await session.commit()
    return {"id": user.id, "username": user.username, "role": user.role,
            "must_change_pw": user.must_change_pw}


@router.get("/ban-check")
async def ban_check(request: Request, session: AsyncSession = Depends(get_session)):
    """Traefik forwardAuth target: 403 if the client IP is banned, else 200.

    Called per-request by the proxy; backed by an in-memory ban cache so the
    hot path is a dict lookup, not a DB query.
    """
    ip = client_ip_from_headers(request)
    if await ban_cache.is_banned(session, ip):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Access temporarily blocked")
    return Response(status_code=status.HTTP_200_OK)


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
    if not stored:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Refresh revoked")
    if stored.revoked:
        # RFC 9700: replay of a rotated token — assume theft, kill the family
        await session.exec(
            update(RefreshToken)
            .where(RefreshToken.family_id == stored.family_id)
            .values(revoked=True)
        )
        await audit_request(session, request, "auth.refresh_reuse",
                            user_id=stored.user_id, resource=stored.family_id)
        await session.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Refresh revoked")
    user = await session.get(User, claims["sub"])
    if not user or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User inactive")
    stored.revoked = True
    session.add(stored)
    await _issue_session(response, session, user, request, family_id=stored.family_id)
    return {"ok": True}


@router.post("/logout")
async def logout(request: Request, response: Response,
                 end_session: bool = False,
                 session: AsyncSession = Depends(get_session)):
    user_id = None
    stored = None
    raw = request.cookies.get("refresh_token")
    if raw:
        try:
            claims = tokens.decode_token(raw)
            user_id = claims.get("sub")
            stored = await session.get(RefreshToken, claims.get("jti"))
        except tokens.TokenError:
            pass

    # An active workstation session blocks a plain logout — the user must
    # explicitly end it (end_session=true) so we don't orphan a live desktop.
    active: list[Workstation] = []
    if user_id:
        result = await session.exec(select(Workstation).where(
            Workstation.occupied_by == user_id,
            Workstation.active_connections > 0))
        active = result.all()
    if active and not end_session:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={"code": "active_session", "count": len(active)})

    # Teardown: flag agents to drop clients and free occupancy immediately.
    for ws in active:
        ws.disconnect_pending = True
        ws.occupied_by = None
        ws.occupied_at = None
        ws.active_connections = 0
        session.add(ws)

    if stored:
        stored.revoked = True
        session.add(stored)
    await audit_request(session, request, "auth.logout", user_id=user_id)
    await session.commit()
    _clear_auth_cookies(response)
    return {"ok": True}


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(get_current_user)):
    return UserOut(id=user.id, username=user.username, email=user.email,
                   role=user.role, is_active=user.is_active)


@router.post("/change-password")
async def change_password(body: ChangePasswordRequest, request: Request, response: Response,
                          session: AsyncSession = Depends(get_session),
                          user: User = Depends(get_current_user)):
    if not verify_password(body.old_password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Current password is incorrect")
    try:
        validate_password(body.new_password, current_policy())
    except ValueError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e))
    user.password_hash = hash_password(body.new_password)
    user.must_change_pw = False
    session.add(user)
    await session.exec(update(RefreshToken)
                       .where(RefreshToken.user_id == user.id)
                       .values(revoked=True))
    await _issue_session(response, session, user, request)
    await audit_request(session, request, "auth.password_change", user_id=user.id)
    await session.commit()
    return {"ok": True}


@router.post("/accept-invite", status_code=201)
async def accept_invite(body: AcceptInviteRequest, request: Request, response: Response,
                        session: AsyncSession = Depends(get_session)):
    result = await session.exec(select(Invite).where(Invite.token_hash == _hash_token(body.token)))
    inv = result.first()
    if not inv or inv.used_at is not None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid or used invite")
    if inv.expires_at:
        expires = inv.expires_at if inv.expires_at.tzinfo else inv.expires_at.replace(tzinfo=timezone.utc)
        if expires < _now():
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invite expired")
    exists = await session.exec(select(User).where(User.username == body.username))
    if exists.first():
        raise HTTPException(status.HTTP_409_CONFLICT, "Username taken")
    try:
        validate_password(body.password, current_policy())
    except ValueError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e))
    user = User(username=body.username, email=inv.email,
                password_hash=hash_password(body.password), role=inv.role)
    inv.used_at = _now()
    session.add_all([user, inv])
    await _issue_session(response, session, user, request)
    await audit_request(session, request, "auth.accept_invite", user_id=user.id,
                        detail={"role": user.role})
    await session.commit()
    return {"id": user.id, "username": user.username, "role": user.role}


@router.get("/link/providers", response_model=list[ConnectedIdentity])
async def linked_providers(user: User = Depends(get_current_user),
                           session: AsyncSession = Depends(get_session)):
    rows = (await session.exec(select(FederatedIdentity).where(
        FederatedIdentity.user_id == user.id))).all()
    return [ConnectedIdentity(provider=r.provider, email=r.email,
                              created_at=r.created_at.isoformat()) for r in rows]


@router.get("/link/{name}/start")
async def link_start(name: str, user: User = Depends(get_current_user),
                     session: AsyncSession = Depends(get_session)):
    provider = (await session.exec(select(OAuthProvider).where(
        OAuthProvider.name == name, OAuthProvider.enabled == True))).first()  # noqa: E712
    if not provider:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "unknown provider")
    url, state, verifier = await oauth.build_authorize(provider, mode="link")
    resp = RedirectResponse(url, status_code=status.HTTP_302_FOUND)
    resp.set_cookie(oauth.TX_COOKIE, oauth.pack_tx(name, state, verifier, "link", user.id),
                    max_age=oauth.TX_TTL, httponly=True,
                    secure=_settings.COOKIE_SECURE, samesite="lax")
    return resp


@router.get("/link/{name}/callback")
async def link_callback(name: str, request: Request,
                        user: User = Depends(get_current_user),
                        session: AsyncSession = Depends(get_session)):
    tx_raw = request.cookies.get(oauth.TX_COOKIE)
    if not tx_raw:
        return RedirectResponse("/?link=missing_state", status_code=302)
    try:
        tx = oauth.unpack_tx(tx_raw)
    except Exception:
        return RedirectResponse("/?link=bad_state", status_code=302)
    if tx["provider"] != name or tx["mode"] != "link" or \
            request.query_params.get("state") != tx["state"]:
        return RedirectResponse("/?link=bad_state", status_code=302)
    if tx["uid"] != user.id:
        return RedirectResponse("/?link=error", status_code=302)
    provider = (await session.exec(select(OAuthProvider).where(
        OAuthProvider.name == name))).first()
    if not provider:
        return RedirectResponse("/?link=error", status_code=302)
    try:
        identity = await oauth.fetch_identity(provider, "link", str(request.url), tx["verifier"])
        await federation.link_identity(session, user, name, identity)
        await audit_request(session, request, "sso.link", user_id=user.id,
                            resource=name, detail={"email": identity.email})
        await session.commit()
    except federation.FederationError:
        return RedirectResponse("/?link=conflict", status_code=302)
    except Exception:
        return RedirectResponse("/?link=error", status_code=302)
    resp = RedirectResponse("/?link=ok", status_code=302)
    resp.delete_cookie(oauth.TX_COOKIE)
    return resp


@router.delete("/link/{name}")
async def unlink_provider(name: str, request: Request, user: User = Depends(get_current_user),
                          session: AsyncSession = Depends(get_session)):
    rows = (await session.exec(select(FederatedIdentity).where(
        FederatedIdentity.user_id == user.id))).all()
    target = next((r for r in rows if r.provider == name), None)
    if not target:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not linked")
    has_password = user.password_hash and not user.password_hash.startswith("!")
    if not has_password and len(rows) <= 1:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "cannot unlink the only login method")
    await session.delete(target)
    await audit_request(session, request, "sso.unlink", user_id=user.id, resource=name)
    await session.commit()
    return {"ok": True}
