import base64
import time
import ipaddress
import re
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse, RedirectResponse
from sqlmodel import select, delete
from sqlmodel.ext.asyncio.session import AsyncSession

from app.config import Settings
from app.database import get_session
from app.models import User, WorkstationEnrollmentToken, Workstation, WorkstationAccess
from app.schemas import (
    EnrollTokenOut, WorkstationAccessUpdate, WorkstationIconUpdate, WorkstationConnectOut, WorkstationOut,
    WorkstationUpdate, WorkstationUpdateCommandOut,
)
from app.security.cookies import clean_cookie_header
from app.security.crypto import decrypt_secret
from app.security.nav import is_navigation, no_access
from app.security.safe_next import safe_next
from app.security.deps import require_admin, get_current_user
from app.services import ws_icon
from app.services.audit import audit_request
from app.services.workstations import (
    kick_unqualified,
    build_enroll_command, build_update_command, get_latest_agent_version, lan_ca_pin,
    lan_enroll_url, sha256_hex,
)

# (workstation, user) -> monotonic expiry of a /connect?force=true takeover grant.
_force_grants: dict[tuple[str, str], float] = {}
_FORCE_TTL_S = 60

router = APIRouter()
# Mounted at /internal/workstations: reachable only by Traefik's forwardAuth.
internal_router = APIRouter()
_settings = Settings()


@router.post("/enroll-tokens", response_model=EnrollTokenOut, status_code=201)
async def mint_enroll_token(request: Request,
                            admin: User = Depends(require_admin),
                            session: AsyncSession = Depends(get_session)):
    raw = secrets.token_urlsafe(32)
    expires = datetime.now(timezone.utc) + timedelta(
        hours=_settings.ENROLL_TOKEN_TTL_HOURS)
    session.add(WorkstationEnrollmentToken(
        token_hash=sha256_hex(raw), created_by=admin.id, expires_at=expires))
    await audit_request(session, request, "workstation.enroll_token_create",
                        user_id=admin.id)
    await session.commit()
    lan_base, lan_source = lan_enroll_url()
    public_base = f"https://{_settings.DOMAIN}"
    lan_command = None
    if lan_base:
        pin, pubkey_pin, cert_created = lan_ca_pin(lan_base)
        if cert_created:
            # publish the fresh cert to Traefik (defaultCertificate config)
            from app.services.route_writer import refresh_routes_from_db
            await refresh_routes_from_db(session)
        lan_command = build_enroll_command(
            raw, lan_base, ca_pin=pin, pubkey_pin=pubkey_pin)
    return EnrollTokenOut(
        token=raw, expires_at=expires.isoformat(),
        lan_command=lan_command,
        public_command=build_enroll_command(raw, public_base),
        lan_url_source=lan_source)


@router.get("/enroll-tokens")
async def list_enroll_tokens(admin: User = Depends(require_admin),
                             session: AsyncSession = Depends(get_session)):
    """Unused, unexpired enrollment tokens (ids only; the secret is never stored)."""
    now = datetime.now(timezone.utc)
    rows = (await session.exec(select(WorkstationEnrollmentToken).where(
        WorkstationEnrollmentToken.used_at == None))).all()  # noqa: E711
    out = []
    for t in rows:
        exp = t.expires_at if t.expires_at.tzinfo else t.expires_at.replace(tzinfo=timezone.utc)
        if exp > now:
            out.append({"id": t.id, "created_by": t.created_by,
                        "created_at": t.created_at.isoformat(),
                        "expires_at": exp.isoformat()})
    return out


@router.delete("/enroll-tokens/{token_id}")
async def revoke_enroll_token(token_id: str, request: Request,
                              admin: User = Depends(require_admin),
                              session: AsyncSession = Depends(get_session)):
    tok = await session.get(WorkstationEnrollmentToken, token_id)
    if tok is None or tok.used_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such unused token")
    await session.delete(tok)
    await audit_request(session, request, "workstation.enroll_token_revoke",
                        user_id=admin.id, resource=token_id)
    await session.commit()
    return {"ok": True}


@router.get("/{ws_id}/update-command", response_model=WorkstationUpdateCommandOut)
async def update_command(ws_id: str,
                         admin: User = Depends(require_admin),
                         session: AsyncSession = Depends(get_session)):
    ws = await _get_or_404(session, ws_id)
    lan_base, lan_source = lan_enroll_url()
    lan_command = None
    if lan_base:
        pin, pubkey_pin, _ = lan_ca_pin(lan_base)
        lan_command = build_update_command(
            lan_base, ca_pin=pin, pubkey_pin=pubkey_pin)
    return WorkstationUpdateCommandOut(
        latest_version=get_latest_agent_version(),
        current_version=ws.agent_version,
        lan_command=lan_command,
        public_command=build_update_command(f"https://{_settings.DOMAIN}"),
        lan_url_source=lan_source)


def _out(ws: Workstation, allowed: list[str],
         occupant: User | None = None,
         viewer_id: str | None = None,
         latest_version: str = "") -> WorkstationOut:
    in_use = ws.active_connections > 0 and ws.occupied_by is not None
    return WorkstationOut(
        id=ws.id, name=ws.name, subdomain=ws.subdomain, hostname=ws.hostname,
        lan_ip=ws.lan_ip, port=ws.port, status=ws.status,
        display_server=ws.display_server, gpu_info=ws.gpu_info,
        os_info=ws.os_info, agent_version=ws.agent_version,
        agent_outdated=bool(latest_version)
        and ws.agent_version not in ("", latest_version),
        stream_settings=ws.stream_settings, all_users=ws.all_users,
        last_heartbeat=ws.last_heartbeat.isoformat() if ws.last_heartbeat else None,
        last_error=ws.last_error, created_at=ws.created_at.isoformat(),
        allowed_user_ids=allowed,
        in_use=in_use,
        in_use_by=occupant.username if (in_use and occupant) else None,
        in_use_self=bool(in_use and viewer_id and ws.occupied_by == viewer_id),
        icon_kind=ws_icon.icon_kind(ws.icon),
        icon_etag=ws_icon.icon_etag(ws.icon, ws.name, ws.id))


async def _occupant(session, ws: Workstation) -> User | None:
    if ws.occupied_by is None:
        return None
    return await session.get(User, ws.occupied_by)


async def _allowed_ids(session, ws_id: str) -> list[str]:
    rows = await session.exec(select(WorkstationAccess).where(
        WorkstationAccess.workstation_id == ws_id))
    return [a.user_id for a in rows.all()]


async def _get_or_404(session, ws_id: str) -> Workstation:
    ws = await session.get(Workstation, ws_id)
    if ws is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Workstation not found")
    return ws


@router.get("", response_model=list[WorkstationOut])
async def list_workstations(admin: User = Depends(require_admin),
                            session: AsyncSession = Depends(get_session)):
    rows = (await session.exec(select(Workstation))).all()
    latest = get_latest_agent_version()
    return [_out(ws, await _allowed_ids(session, ws.id),
                 occupant=await _occupant(session, ws), viewer_id=admin.id,
                 latest_version=latest)
            for ws in rows]


def _redirect_host(request: Request) -> str:
    """X-Forwarded-Host mirrors the client's Host header, so it is
    attacker-influenced — only honor hosts we actually serve: the public
    domain, the configured LAN URL, or a private/loopback address (the LAN
    routers are host-agnostic). Anything else falls back to DOMAIN. A
    non-standard port (from the host or X-Forwarded-Port) is kept for an
    honored host: validation is on the hostname, the port is digits only."""
    raw = request.headers.get("x-forwarded-host", "").split(",")[0].strip().lower()
    if not raw or not re.fullmatch(r"[a-z0-9.\-]+(:\d{1,5})?", raw):
        return _settings.DOMAIN
    host, _, port = raw.partition(":")
    if not port:
        xp = request.headers.get("x-forwarded-port", "").split(",")[0].strip()
        port = xp if re.fullmatch(r"\d{1,5}", xp) and xp not in ("80", "443") else ""
    if port and not 0 < int(port) < 65536:
        port = ""
    with_port = f"{host}:{port}" if port else host
    allowed = {_settings.DOMAIN.lower().partition(":")[0]}
    if _settings.SERVER_LAN_URL:
        allowed.add(_settings.SERVER_LAN_URL.split("://", 1)[-1].rstrip("/")
                    .lower().partition(":")[0])
    if host in allowed:
        return with_port
    try:
        addr = ipaddress.ip_address(host)
        if addr.is_private or addr.is_loopback:
            return with_port
    except ValueError:
        pass
    return _settings.DOMAIN


def _unauthenticated(request: Request, msg: str):
    """401 for ws/XHR; 302 to the login page for browser navigations —
    Traefik relays a forwardAuth non-2xx response (incl. Location) verbatim,
    so without this an expired cookie shows raw JSON at /w/{sub}/."""
    if not is_navigation(request):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, msg)
    uri = request.headers.get("x-forwarded-uri", "")
    # Absolute URL required: Traefik resolves a relative Location against
    # the auth-server address (http://backend:8000), not the original host.
    proto = request.headers.get("x-forwarded-proto", "https")
    if proto not in ("http", "https"):
        proto = "https"
    target = f"{proto}://{_redirect_host(request)}/login"
    # next= only for known-shape stream paths passing the shared rule.
    if re.match(r"/w/[a-z0-9-]+(/|\Z)", uri) and safe_next(uri):
        target += f"?next={quote(uri, safe='/')}"
    return RedirectResponse(target, status_code=302)


@internal_router.get("/{ws_id}/auth-check")
async def auth_check(ws_id: str, request: Request,
                     session: AsyncSession = Depends(get_session)):
    """Traefik forwardAuth target gating /w/ stream routes. 200 = allow.

    Served under /internal (never routed by Traefik) and authenticated only by
    the styx_proxy cookie: it mutates seat occupancy, so it must not be public.
    The workstation comes from the router's auth address (route_writer emits
    one per workstation), never from parsing the request, so Traefik's routing
    and this check cannot disagree about which desktop is being opened.
    """
    from app.security.deps import proxy_user_or_none
    user = await proxy_user_or_none(request, session)
    if user is None:
        return _unauthenticated(request, "Not authenticated")
    uri = request.headers.get("x-forwarded-uri", "")
    ws = await session.get(Workstation, ws_id)
    if ws is None:
        return no_access(request, "Unknown workstation")
    allowed = await _allowed_ids(session, ws.id)
    if not (user.role == "admin" or ws.all_users or user.id in allowed):
        return no_access(request, "No access")
    # A websocket upgrade passing auth = someone is (re)taking the desktop.
    # Record who; the agent's connection count decides whether it's live.
    if "/websocket" in uri:
        # Takeover lock: another user's live seat needs /connect?force=true,
        # which hands the seat over; opening the URL directly is refused.
        # Not popped: a parallel websocket must pass too; the grant simply expires.
        granted = _force_grants.get((ws.id, user.id), 0) > time.monotonic()
        if (ws.active_connections > 0 and ws.occupied_by
                and ws.occupied_by != user.id and not granted):
            return no_access(request, "Workstation in use")
        ws.occupied_by = user.id
        ws.occupied_at = datetime.now(timezone.utc)
        session.add(ws)
        await session.commit()
    headers = clean_cookie_header(request)
    if ws.selkies_password_enc:
        # Traefik copies this onto the upstream request (authResponseHeaders)
        creds = base64.b64encode(
            f"styx:{decrypt_secret(ws.selkies_password_enc)}".encode()).decode()
        headers = {**headers, "Authorization": f"Basic {creds}"}
    return JSONResponse({"ok": True}, headers=headers)


@router.get("/mine", response_model=list[WorkstationOut])
async def my_workstations(user: User = Depends(get_current_user),
                          session: AsyncSession = Depends(get_session)):
    rows = (await session.exec(select(Workstation).where(
        Workstation.status != "revoked"))).all()
    out = []
    for ws in rows:
        allowed = await _allowed_ids(session, ws.id)
        if user.role == "admin" or ws.all_users or user.id in allowed:
            out.append(_out(ws, [], occupant=await _occupant(session, ws),
                            viewer_id=user.id))
    return out


@router.get("/{ws_id}/connect", response_model=WorkstationConnectOut)
async def connect_url(ws_id: str, force: bool = False,
                      user: User = Depends(get_current_user),
                      session: AsyncSession = Depends(get_session)):
    ws = await _get_or_404(session, ws_id)
    allowed = await _allowed_ids(session, ws.id)
    if not (user.role == "admin" or ws.all_users or user.id in allowed):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "No access to this workstation")
    if ws.status != "online":
        raise HTTPException(status.HTTP_409_CONFLICT,
                            f"Workstation is {ws.status}, not online")
    # Single-user desktop: a second user joining shares (and fights over)
    # the same screen/input. Block unless it's the occupant reconnecting
    # or an explicit force-takeover.
    if (ws.active_connections > 0 and ws.occupied_by
            and ws.occupied_by != user.id and not force):
        occ = await _occupant(session, ws)
        raise HTTPException(
            status.HTTP_423_LOCKED,
            f"In use by {occ.username if occ else 'another user'}")
    if force:
        _force_grants[(ws.id, user.id)] = time.monotonic() + _FORCE_TTL_S
    url = f"https://{_settings.DOMAIN}/w/{ws.subdomain}/"
    return WorkstationConnectOut(url=url)


@router.patch("/{ws_id}", response_model=WorkstationOut)
async def update_workstation(ws_id: str, body: WorkstationUpdate,
                             request: Request,
                             admin: User = Depends(require_admin),
                             session: AsyncSession = Depends(get_session)):
    ws = await _get_or_404(session, ws_id)
    if body.name is not None:
        ws.name = body.name
    if body.all_users is not None:
        ws.all_users = body.all_users
    if body.stream_settings is not None:
        ws.stream_settings = body.stream_settings
    session.add(ws)
    await session.flush()
    await kick_unqualified(session, ws_id=ws.id)
    await audit_request(session, request, "workstation.update",
                        user_id=admin.id, resource=ws.id)
    await session.commit()
    return _out(ws, await _allowed_ids(session, ws.id))


@router.put("/{ws_id}/icon", response_model=WorkstationOut)
async def set_icon(ws_id: str, body: WorkstationIconUpdate, request: Request,
                   admin: User = Depends(require_admin),
                   session: AsyncSession = Depends(get_session)):
    ws = await _get_or_404(session, ws_id)
    try:
        ws.icon = ws_icon.validate_icon(body.kind, body.value)
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))
    session.add(ws)
    await audit_request(session, request, "workstation.icon_change",
                        user_id=admin.id, resource=ws.id,
                        detail={"kind": body.kind})
    await session.commit()
    return _out(ws, await _allowed_ids(session, ws.id))


@router.get("/{ws_id}/icon")
async def get_icon(ws_id: str, request: Request,
                   user: User = Depends(get_current_user),
                   session: AsyncSession = Depends(get_session)):
    ws = await _get_or_404(session, ws_id)
    allowed = await _allowed_ids(session, ws.id)
    if not (user.role == "admin" or ws.all_users or user.id in allowed):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "No access to this workstation")
    return ws_icon.icon_response(request, ws.icon, ws.name, ws.id)


@router.put("/{ws_id}/access", response_model=WorkstationOut)
async def set_access(ws_id: str, body: WorkstationAccessUpdate,
                     request: Request,
                     admin: User = Depends(require_admin),
                     session: AsyncSession = Depends(get_session)):
    ws = await _get_or_404(session, ws_id)
    await session.exec(delete(WorkstationAccess).where(
        WorkstationAccess.workstation_id == ws.id))
    for uid in set(body.user_ids):
        session.add(WorkstationAccess(workstation_id=ws.id, user_id=uid))
    await session.flush()
    await kick_unqualified(session, ws_id=ws.id)
    await audit_request(session, request, "workstation.access_change",
                        user_id=admin.id, resource=ws.id,
                        detail={"user_ids": body.user_ids})
    await session.commit()
    return _out(ws, await _allowed_ids(session, ws.id))


@router.delete("/{ws_id}")
async def delete_workstation(ws_id: str, request: Request, purge: bool = False,
                             admin: User = Depends(require_admin),
                             session: AsyncSession = Depends(get_session)):
    ws = await _get_or_404(session, ws_id)
    if purge:
        await session.exec(delete(WorkstationAccess).where(
            WorkstationAccess.workstation_id == ws.id))
        await audit_request(session, request, "workstation.purge",
                            user_id=admin.id, resource=ws.id)
        await session.delete(ws)
    else:
        ws.status = "revoked"
        session.add(ws)
        await audit_request(session, request, "workstation.revoke",
                            user_id=admin.id, resource=ws.id)
    await session.commit()
    from app.services.route_writer import refresh_routes_from_db
    await refresh_routes_from_db(session)
    return {"ok": True}
