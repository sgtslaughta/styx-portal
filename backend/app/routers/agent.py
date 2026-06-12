"""Agent-facing endpoints. Auth: per-workstation bearer token (hashed at rest).

CSRF-exempt by path prefix (see main.py) — agents are header-authenticated,
no cookies, so cross-site request forgery does not apply.
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlmodel import select, delete
from sqlmodel.ext.asyncio.session import AsyncSession

from app.config import Settings
from app.database import get_session
from app.models import Workstation, WorkstationAccess
from app.schemas import WorkstationHeartbeatRequest, WorkstationHeartbeatResponse
from app.services.audit import audit_request
from app.services.workstations import sha256_hex

router = APIRouter()
_settings = Settings()


async def get_agent_workstation(
        request: Request,
        session: AsyncSession = Depends(get_session)) -> Workstation:
    auth = request.headers.get("authorization", "")
    if not auth.lower().startswith("bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Agent token required")
    token_hash = sha256_hex(auth[7:].strip())
    result = await session.exec(select(Workstation).where(
        Workstation.agent_token_hash == token_hash))
    ws = result.first()
    if ws is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Unknown agent token")
    return ws


@router.post("/heartbeat", response_model=WorkstationHeartbeatResponse)
async def heartbeat(body: WorkstationHeartbeatRequest,
                    ws: Workstation = Depends(get_agent_workstation),
                    session: AsyncSession = Depends(get_session)):
    if ws.status == "revoked":
        return WorkstationHeartbeatResponse(
            state="revoked", stream_settings={},
            heartbeat_interval_s=_settings.WORKSTATION_HEARTBEAT_S)
    routes_dirty = ws.status != "online" or bool(body.lan_ip and body.lan_ip != ws.lan_ip)
    ws.status = "online"
    if body.lan_ip:
        ws.lan_ip = body.lan_ip
    ws.last_heartbeat = datetime.now(timezone.utc)
    ws.last_error = body.last_error
    # Occupancy: the agent's gateway counts live stream websockets; the
    # occupant's identity comes from forward-auth. Zero connections clears it.
    conns = body.health.get("active_connections")
    if isinstance(conns, int) and conns >= 0:
        ws.active_connections = conns
        if conns == 0:
            ws.occupied_by = None
            ws.occupied_at = None
    session.add(ws)
    await session.commit()
    if routes_dirty:
        from app.services.route_writer import refresh_routes_from_db
        await refresh_routes_from_db(session)
    return WorkstationHeartbeatResponse(
        state="ok", stream_settings=ws.stream_settings,
        heartbeat_interval_s=_settings.WORKSTATION_HEARTBEAT_S)


@router.post("/deregister")
async def deregister(request: Request,
                     ws: Workstation = Depends(get_agent_workstation),
                     session: AsyncSession = Depends(get_session)):
    await session.exec(delete(WorkstationAccess).where(
        WorkstationAccess.workstation_id == ws.id))
    await audit_request(session, request, "workstation.deregister",
                        resource=ws.id, detail={"hostname": ws.hostname,
                                               "agent_version": ws.agent_version,
                                               "lan_ip": ws.lan_ip})
    await session.delete(ws)
    await session.commit()
    from app.services.route_writer import refresh_routes_from_db
    await refresh_routes_from_db(session)
    return {"ok": True}
