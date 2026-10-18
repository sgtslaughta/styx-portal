import asyncio
import hashlib
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse
from sqlmodel import select, update
from sqlmodel.ext.asyncio.session import AsyncSession

from app.config import Settings
from app.database import get_session
from app.models import User, Invite, RefreshToken, Instance, ServiceTemplate, OAuthProvider, FederatedIdentity, Workstation
from app.schemas import SetupRequest, LoginRequest, AcceptInviteRequest, UserOut, ConnectedIdentity, ChangePasswordRequest, OpenPreferences
from app.security import tokens, oauth, setup_token
from app.security.passwords import hash_password, verify_password, validate_password, current_policy
from app.security.cookies import (DEVICE_COOKIE, TX_PATH, clear_auth_cookies, set_auth_cookies,
                                  set_device_cookie)
from app.security.csrf import new_csrf_token, CSRF_COOKIE
from app.security.deps import get_current_user
from app.security.setup_gate import users_exist
from app.services import federation, single_use
from app.services.audit import audit_request
from app.middleware.rate_limit import client_ip_from_headers, client_ip_resolved
from app.services.abuse import fail_tracker, ban_cache, ban_ip, login_lockout
from app.services.settings_store import settings as sys_settings

router = APIRouter()
logger = logging.getLogger("styx-portal")
_settings = Settings()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt: datetime) -> datetime:
    """Treat a naive datetime (as SQLite returns) as UTC for comparison."""
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


_DUMMY: str | None = None


def _dummy_hash() -> str:
    """A valid Argon2 hash to verify against when the user is missing/locked (uniform timing)."""
    global _DUMMY
    if _DUMMY is None:
        _DUMMY = hash_password("styx-dummy-password")
    return _DUMMY


def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


async def _issue_session(resp: Response, session: AsyncSession, user: User, request: Request,
                         family_id: str | None = None) -> None:
    access = tokens.create_access_token(user.id, user.role, tv=user.token_version)
    refresh, jti = tokens.create_refresh_token(user.id)
    family_id = family_id or jti
    session.add(RefreshToken(
        jti=jti, user_id=user.id,
        family_id=family_id,
        expires_at=_now() + timedelta(seconds=sys_settings.get("REFRESH_TTL")),
        user_agent=request.headers.get("user-agent"),
    ))
    user.last_login = _now()
    session.add(user)
    await session.commit()
    set_auth_cookies(resp, access, refresh, tokens.create_proxy_token(user.id, family_id, tv=user.token_version),
                     new_csrf_token())


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
    if request.headers.get("sec-fetch-site", "same-origin") not in ("same-origin", "none"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Cross-site setup refused")
    if await users_exist(session):
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    if not setup_token.verify(body.setup_token):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Invalid setup code")
    try:
        validate_password(body.password, current_policy())
    except ValueError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e))
    async with setup_token.setup_lock:
        if await users_exist(session):  # lost the race to a concurrent request
            raise HTTPException(status.HTTP_404_NOT_FOUND)
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
    setup_token.clear()
    return UserOut(id=user.id, username=user.username, email=user.email,
                   role=user.role, is_active=user.is_active)


@router.post("/login")
async def login(body: LoginRequest, request: Request, response: Response,
                session: AsyncSession = Depends(get_session)):
    ip, resolved = client_ip_resolved(request)
    if not resolved:
        logger.error("client IP not resolved; check DEPLOY_MODE/TRUSTED_PROXY_CIDRS "
                     "(per-IP ban and tracking skipped for this login)")
    result = await session.exec(select(User).where(User.username == body.username))
    user = result.first()

    # Per-(username, IP) lockout. A locked attempt is indistinguishable from a bad
    # password (same 401, same Argon2 work), so lockout never reveals which names exist.
    # A valid trusted-device cookie for this very account skips the lock and the
    # distributed throttle (not Argon2, not the per-IP ban): the owner is never shut out.
    # Each device token has its own failure budget; once spent it bypasses nothing.
    rnd = tokens.device_rnd(request.cookies.get(DEVICE_COOKIE), user)
    device_ok = rnd is not None and not login_lockout.device_blocked(rnd)
    if not device_ok and (
            login_lockout.is_locked(body.username, ip)
            or login_lockout.throttled(body.username, _settings.LOGIN_GLOBAL_THRESHOLD,
                                       sys_settings.get("LOCKOUT_DURATION"))):
        verify_password(body.password, _dummy_hash())
        await audit_request(session, request, "auth.login_locked",
                            user_id=user.id if user else None)
        await session.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")

    ok = bool(user and user.is_active)
    pw_ok = verify_password(body.password, user.password_hash if ok else _dummy_hash())
    if not (ok and pw_ok):
        # Only real accounts are tracked (keeps the maps bounded by the user count and
        # un-floodable); the response path is identical either way.
        if rnd:
            login_lockout.device_fail(rnd, sys_settings.get("LOCKOUT_THRESHOLD"),
                                      sys_settings.get("LOCKOUT_DURATION"))
        if user:
            login_lockout.record_fail(body.username, ip, sys_settings.get("LOCKOUT_THRESHOLD"),
                                      sys_settings.get("LOCKOUT_DURATION"))
        # Per-IP abuse detector -> proxy ban (L3). Thresholds are live-tunable.
        fail_tracker.threshold = sys_settings.get("BAN_FAIL_THRESHOLD")
        fail_tracker.window = sys_settings.get("BAN_FAIL_WINDOW")
        if resolved and fail_tracker.record(ip):
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
    login_lockout.clear(body.username, ip)
    if rnd:
        login_lockout.device_clear(rnd)    # the fresh cookie below carries a new rnd
    session.add(user)
    await _issue_session(response, session, user, request)
    set_device_cookie(response, tokens.create_device_token(user.id, user.token_version))
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
    # Atomic claim: only one concurrent use of a refresh token can win the rotation.
    claimed = 0
    if not stored.revoked:
        res = await session.exec(update(RefreshToken).where(
            RefreshToken.jti == stored.jti, RefreshToken.revoked == False)  # noqa: E712
            .values(revoked=True))
        claimed = res.rowcount
    if not claimed:
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
    root = await session.get(RefreshToken, stored.family_id) or stored
    if _now() - _aware(root.created_at) > timedelta(seconds=_settings.SESSION_MAX_AGE):
        await session.exec(update(RefreshToken).where(
            RefreshToken.family_id == stored.family_id).values(revoked=True))
        await session.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session expired")
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
        # Whole family: a forked/rotated sibling must not keep the proxy cookie alive.
        await session.exec(update(RefreshToken).where(
            RefreshToken.family_id == (stored.family_id or stored.jti)).values(revoked=True))
        stored.revoked = True
        session.add(stored)
    # Hard kill-on-logout: revoke the current access-token jti so the stateless
    # token can't be replayed until exp (e.g. to reconnect a workstation stream).
    araw = request.cookies.get("access_token")
    if araw:
        try:
            aclaims = tokens.decode_token(araw)
            if aclaims.get("jti") and aclaims.get("exp"):
                from app.services import token_denylist
                await token_denylist.revoke_access(
                    session, aclaims["jti"],
                    datetime.fromtimestamp(aclaims["exp"], tz=timezone.utc))
        except tokens.TokenError:
            pass
    await audit_request(session, request, "auth.logout", user_id=user_id)
    await session.commit()
    clear_auth_cookies(response)
    return {"ok": True}


def _me_out(user: User) -> UserOut:
    return UserOut(id=user.id, username=user.username, email=user.email, role=user.role,
                   is_active=user.is_active, open_workspaces=user.open_workspaces,
                   open_apps=user.open_apps)


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(get_current_user)):
    return _me_out(user)


@router.put("/me/preferences", response_model=UserOut)
async def set_preferences(body: OpenPreferences, session: AsyncSession = Depends(get_session),
                          user: User = Depends(get_current_user)):
    """Personal UI preference: no admin override, no audit entry."""
    row = await session.get(User, user.id)
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(row, k, v)
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return _me_out(row)


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
    user.token_version += 1     # kills every access token minted before this change
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
    if not await single_use.claim(session, Invite, inv.id):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid or used invite")
    user = User(username=body.username, email=inv.email,
                password_hash=hash_password(body.password), role=inv.role)
    session.add(user)
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
                    secure=_settings.COOKIE_SECURE, samesite="lax", path=TX_PATH)
    return resp


def _link_redirect(code: str) -> RedirectResponse:
    resp = RedirectResponse(f"/?link={code}", status_code=302)
    resp.delete_cookie(oauth.TX_COOKIE, path=TX_PATH)
    return resp


@router.get("/link/{name}/callback")
async def link_callback(name: str, request: Request,
                        user: User = Depends(get_current_user),
                        session: AsyncSession = Depends(get_session)):
    tx_raw = request.cookies.get(oauth.TX_COOKIE)
    if not tx_raw:
        return _link_redirect("missing_state")
    try:
        tx = oauth.unpack_tx(tx_raw)
    except Exception:
        return _link_redirect("bad_state")
    if tx["provider"] != name or tx["mode"] != "link" or \
            request.query_params.get("state") != tx["state"]:
        return _link_redirect("bad_state")
    if tx["uid"] != user.id:
        return _link_redirect("error")
    provider = (await session.exec(select(OAuthProvider).where(
        OAuthProvider.name == name))).first()
    if not provider:
        return _link_redirect("error")
    try:
        identity = await oauth.fetch_identity(provider, "link", str(request.url), tx["verifier"])
        await federation.link_identity(session, user, name, identity)
        await audit_request(session, request, "sso.link", user_id=user.id,
                            resource=name, detail={"email": identity.email})
        await session.commit()
    except federation.FederationError:
        return _link_redirect("conflict")
    except Exception:
        return _link_redirect("error")
    return _link_redirect("ok")


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
