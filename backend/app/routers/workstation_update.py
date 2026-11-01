"""Admin routes that order workstation agents to self-update.

Registered before the main workstations router so the literal
/agent-update-outdated path is not captured by /{ws_id}.
"""
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.database import get_session
from app.models import User, Workstation
from app.schemas import WorkstationOut
from app.security.deps import require_admin
from app.services.audit import audit_request
from app.services.workstations import can_self_update, get_latest_agent_version, request_agent_update

router = APIRouter()


def _outdated(ws: Workstation, latest: str) -> bool:
    return bool(latest) and ws.agent_version not in ("", latest)


@router.post("/agent-update-outdated")
async def update_outdated(request: Request,
                          admin: User = Depends(require_admin),
                          session: AsyncSession = Depends(get_session)):
    latest = get_latest_agent_version()
    rows = (await session.exec(select(Workstation).where(
        Workstation.status == "online"))).all()
    n = 0
    for ws in rows:
        if _outdated(ws, latest) and can_self_update(ws.agent_version):
            request_agent_update(ws, latest)
            session.add(ws)
            n += 1
    await audit_request(session, request, "workstation.agent_update_outdated",
                        user_id=admin.id, detail={"requested": n, "version": latest})
    await session.commit()
    return {"requested": n}


@router.post("/{ws_id}/agent-update", response_model=WorkstationOut)
async def update_one(ws_id: str, request: Request,
                     admin: User = Depends(require_admin),
                     session: AsyncSession = Depends(get_session)):
    from app.routers.workstations import _allowed_ids, _get_or_404, _out
    ws = await _get_or_404(session, ws_id)
    latest = get_latest_agent_version()
    if not latest:
        raise HTTPException(status.HTTP_409_CONFLICT, "Latest agent version unknown")
    if ws.agent_version == latest:
        raise HTTPException(status.HTTP_409_CONFLICT, "Agent is already up to date")
    if not can_self_update(ws.agent_version):
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "Agent too old to update itself; run the manual update command once")
    request_agent_update(ws, latest)
    session.add(ws)
    await audit_request(session, request, "workstation.agent_update",
                        user_id=admin.id, resource=ws.id, detail={"version": latest})
    await session.commit()
    return _out(ws, await _allowed_ids(session, ws.id), latest_version=latest)
