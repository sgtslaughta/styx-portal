import re
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlmodel import select, delete
from sqlmodel.ext.asyncio.session import AsyncSession

from app.config import Settings
from app.database import get_session
from app.models import User, WorkstationEnrollmentToken, Workstation, WorkstationAccess
from app.schemas import (
    EnrollTokenOut, WorkstationAccessUpdate, WorkstationConnectOut, WorkstationOut,
    WorkstationUpdate,
)
from app.security.deps import require_admin, get_current_user
from app.services.audit import audit_request
from app.services.workstations import (
    build_enroll_command, lan_enroll_url, sha256_hex,
)

router = APIRouter()
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
    return EnrollTokenOut(
        token=raw, expires_at=expires.isoformat(),
        lan_command=build_enroll_command(raw, lan_base) if lan_base else None,
        public_command=build_enroll_command(raw, public_base),
        lan_url_source=lan_source)


def _out(ws: Workstation, allowed: list[str]) -> WorkstationOut:
    return WorkstationOut(
        id=ws.id, name=ws.name, subdomain=ws.subdomain, hostname=ws.hostname,
        lan_ip=ws.lan_ip, port=ws.port, status=ws.status,
        display_server=ws.display_server, gpu_info=ws.gpu_info,
        os_info=ws.os_info, agent_version=ws.agent_version,
        stream_settings=ws.stream_settings, all_users=ws.all_users,
        last_heartbeat=ws.last_heartbeat.isoformat() if ws.last_heartbeat else None,
        last_error=ws.last_error, created_at=ws.created_at.isoformat(),
        allowed_user_ids=allowed)


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
    return [_out(ws, await _allowed_ids(session, ws.id)) for ws in rows]


@router.get("/auth-check")
async def auth_check(request: Request,
                     session: AsyncSession = Depends(get_session)):
    """Traefik forwardAuth target gating /w/ stream routes. 200 = allow."""
    from app.security import tokens as _tokens
    raw = request.cookies.get("access_token")
    if not raw:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    try:
        claims = _tokens.decode_token(raw)
    except _tokens.TokenError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token")
    user = await session.get(User, claims.get("sub"))
    if not user or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User inactive")
    uri = request.headers.get("x-forwarded-uri", "")
    m = re.match(r"^/w/([a-z0-9-]+)", uri)
    if not m:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Unknown stream path")
    result = await session.exec(select(Workstation).where(
        Workstation.subdomain == m.group(1)))
    ws = result.first()
    if ws is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Unknown workstation")
    allowed = await _allowed_ids(session, ws.id)
    if not (user.role == "admin" or ws.all_users or user.id in allowed):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "No access")
    return {"ok": True}


@router.get("/mine", response_model=list[WorkstationOut])
async def my_workstations(user: User = Depends(get_current_user),
                          session: AsyncSession = Depends(get_session)):
    rows = (await session.exec(select(Workstation).where(
        Workstation.status != "revoked"))).all()
    out = []
    for ws in rows:
        allowed = await _allowed_ids(session, ws.id)
        if user.role == "admin" or ws.all_users or user.id in allowed:
            out.append(_out(ws, []))
    return out


@router.get("/{ws_id}/connect", response_model=WorkstationConnectOut)
async def connect_url(ws_id: str, user: User = Depends(get_current_user),
                      session: AsyncSession = Depends(get_session)):
    ws = await _get_or_404(session, ws_id)
    allowed = await _allowed_ids(session, ws.id)
    if not (user.role == "admin" or ws.all_users or user.id in allowed):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "No access to this workstation")
    if ws.status != "online":
        raise HTTPException(status.HTTP_409_CONFLICT,
                            f"Workstation is {ws.status}, not online")
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
    await audit_request(session, request, "workstation.update",
                        user_id=admin.id, resource=ws.id)
    await session.commit()
    return _out(ws, await _allowed_ids(session, ws.id))


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
