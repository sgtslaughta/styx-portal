"""Agent-facing endpoints. Auth: per-workstation bearer token (hashed at rest).

CSRF-exempt by path prefix (see main.py) — agents are header-authenticated,
no cookies, so cross-site request forgery does not apply.
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlmodel import select, delete
from sqlmodel.ext.asyncio.session import AsyncSession

from app.config import Settings
from app.database import get_session
from app.models import Workstation, WorkstationAccess
from app.schemas import WorkstationHeartbeatRequest, WorkstationHeartbeatResponse
from app.services import stream_sessions, ws_icon, ws_thumb
from app.services.audit import audit_request
from app.services.workstations import (
    build_update_manifest, can_self_update, get_latest_agent_version, request_agent_update, sha256_hex,
)
from app.services.settings_store import settings as _sys_settings
from app.services.ws_settings import resolve_stream_settings, stream_sys_settings
from app.services.turn_usage import record_turn_usage, turn_over_budget

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
    # Persist the running agent's version — a lightweight update (pull + restart,
    # no re-enroll) only surfaces here, so without this 'outdated' never clears.
    ver = body.health.get("agent_version")
    if isinstance(ver, str) and ver:
        ws.agent_version = ver
    _apply_update_report(ws, body.health.get("update"))
    latest = get_latest_agent_version()
    if (ws.update_target and ws.agent_version == ws.update_target
            and ws.update_state != "ok"):
        ws.update_state = "ok"
        ws.update_at = datetime.now(timezone.utc)
    elif (_sys_settings.get("AGENT_AUTO_UPDATE") and latest
            and ws.agent_version not in ("", latest)
            and can_self_update(ws.agent_version)
            and not (ws.update_target == latest
                     and ws.update_state in ("requested", "updating", "rolled_back", "failed"))):
        request_agent_update(ws, latest)
    # Attribute relayed bytes before occupancy may clear (final delta of a session).
    turn_bytes = body.health.get("turn_bytes")
    relayed = isinstance(turn_bytes, int) and not isinstance(turn_bytes, bool) and turn_bytes > 0
    await record_turn_usage(session, ws, turn_bytes)
    if relayed:
        await stream_sessions.mark_relayed(session, ws, body.relay_reason)
    # Occupancy: the agent's gateway counts live stream websockets; the
    # occupant's identity comes from forward-auth. Zero connections clears it.
    conns = body.health.get("active_connections")
    if isinstance(conns, int) and conns >= 0:
        ws.active_connections = conns
        if conns == 0:
            ws.occupied_by = None
            ws.occupied_at = None
            # Re-arm the idle latch: a future session starts fresh.
            ws.idle_disconnect_sent = False
    await stream_sessions.sync_workstation(session, ws)   # idempotent open/close
    if relayed:
        await stream_sessions.mark_relayed(session, ws, body.relay_reason)
    # Resolve effective stream settings: per-workstation override else system default.
    sys_settings_dict = stream_sys_settings(_sys_settings)
    sys_settings_dict["TURN_OVER_BUDGET"] = await turn_over_budget(session)
    effective_ss = resolve_stream_settings(ws.stream_settings, sys_settings_dict,
                                           ws.agent_version)
    idle_timeout = effective_ss["idle_timeout_s"]
    idle_enabled = effective_ss["idle_timeout_enabled"]
    # Idle disconnect backstop: the agent reports seconds since the last
    # client->server input. If an occupied seat has been idle past the timeout,
    # drop it (the release flow fires when the client count hits 0). Skipped
    # when idle timeout is disabled.
    idle_s = body.health.get("idle_seconds")
    if (idle_enabled
            and isinstance(conns, int) and conns > 0
            and isinstance(idle_timeout, (int, float)) and idle_timeout > 0
            and isinstance(idle_s, (int, float)) and idle_s >= idle_timeout
            and not ws.idle_disconnect_sent):
        ws.disconnect_pending = True
        # Latch: don't re-issue until connections drop to 0. An idle browser
        # that auto-reconnects keeps conns > 0, so without this the gateway
        # would be told to restart every heartbeat (502 loop).
        ws.idle_disconnect_sent = True
    # One-shot disconnect: consume the flag set by logout teardown.
    disconnect = ws.disconnect_pending
    if disconnect:
        ws.disconnect_pending = False
    session.add(ws)
    await session.commit()
    if routes_dirty:
        from app.services.route_writer import refresh_routes_from_db
        await refresh_routes_from_db(session)
    return WorkstationHeartbeatResponse(
        state="ok", stream_settings=effective_ss,
        heartbeat_interval_s=_settings.WORKSTATION_HEARTBEAT_S,
        disconnect_clients=disconnect,
        icon_etag=ws_icon.icon_etag(ws.icon, ws.name, ws.id),
        update=({"version": ws.update_target}
                if ws.update_state == "requested"
                and ws.agent_version != ws.update_target else None))


def _apply_update_report(ws: Workstation, rep) -> None:
    """Copy the agent's self-update progress; only for the ordered target."""
    if not isinstance(rep, dict) or not ws.update_target or rep.get("to") != ws.update_target:
        return
    state = rep.get("state")
    if state not in ("updating", "ok", "rolled_back", "failed"):
        return
    err = rep.get("error")
    ws.update_state = state
    ws.update_error = str(err)[:500] if err else None
    ws.update_at = datetime.now(timezone.utc)


@router.get("/update-manifest")
async def update_manifest(ws: Workstation = Depends(get_agent_workstation)):
    return build_update_manifest()


@router.get("/icon")
async def icon(request: Request, ws: Workstation = Depends(get_agent_workstation)):
    return ws_icon.icon_response(request, ws.icon, ws.name, ws.id)


@router.post("/thumbnail", status_code=204)
async def thumbnail(request: Request, ws: Workstation = Depends(get_agent_workstation)):
    if int(request.headers.get("content-length") or 0) > ws_thumb.MAX_BYTES:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "Thumbnail too large")
    data = bytearray()   # streamed + capped: chunked bodies carry no Content-Length
    async for chunk in request.stream():
        data += chunk
        if len(data) > ws_thumb.MAX_BYTES:
            raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "Thumbnail too large")
    data = bytes(data)
    if data[:3] != b"\xff\xd8\xff":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Not a JPEG")
    ws_thumb.write(ws.id, data)
    return Response(status_code=204)


@router.post("/deregister")
async def deregister(request: Request,
                     ws: Workstation = Depends(get_agent_workstation),
                     session: AsyncSession = Depends(get_session)):
    await stream_sessions.close_session(session, "workstation", ws.id)
    await session.exec(delete(WorkstationAccess).where(
        WorkstationAccess.workstation_id == ws.id))
    await audit_request(session, request, "workstation.deregister",
                        resource=ws.id, detail={"hostname": ws.hostname,
                                               "agent_version": ws.agent_version,
                                               "lan_ip": ws.lan_ip})
    await session.delete(ws)
    await session.commit()
    ws_thumb.delete(ws.id)
    from app.services.route_writer import refresh_routes_from_db
    await refresh_routes_from_db(session)
    return {"ok": True}
