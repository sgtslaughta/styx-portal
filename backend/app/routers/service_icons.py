"""Proxied service icons: serve, set by hand, re-fetch from the app (spec: service favicons)."""
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlmodel.ext.asyncio.session import AsyncSession

from app.database import get_session
from app.models import User
from app.routers.services import _get_or_404, _out, _preset_map, get_docker_manager
from app.routers.services_auth import user_may_open
from app.schemas import ProxiedServiceOut, WorkstationIconUpdate
from app.security.deps import get_current_user, require_admin
from app.services import service_favicon, ws_icon
from app.services.audit import audit_request
from app.services.docker_manager import DockerManager

router = APIRouter()


@router.get("/{sid}/icon")
async def get_icon(sid: str, request: Request, user: User = Depends(get_current_user),
                   session: AsyncSession = Depends(get_session)):
    s = await _get_or_404(session, sid)
    if not await user_may_open(session, user, s):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Service not found")   # don't leak existence
    return ws_icon.icon_response(request, s.icon, s.name, s.id)


@router.put("/{sid}/icon", response_model=ProxiedServiceOut)
async def set_icon(sid: str, body: WorkstationIconUpdate, request: Request,
                   admin: User = Depends(require_admin),
                   session: AsyncSession = Depends(get_session)):
    s = await _get_or_404(session, sid)
    try:
        s.icon = ws_icon.validate_icon(body.kind, body.value)
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))
    s.icon_custom = True
    session.add(s)
    await audit_request(session, request, "service.icon_change", user_id=admin.id,
                        resource=s.id, detail={"kind": body.kind})
    await session.commit()
    await session.refresh(s)
    return _out(s, await _preset_map(session))


@router.post("/{sid}/icon/refresh", response_model=ProxiedServiceOut)
async def refresh_icon(sid: str, request: Request, admin: User = Depends(require_admin),
                       session: AsyncSession = Depends(get_session),
                       docker: DockerManager = Depends(get_docker_manager)):
    s = await _get_or_404(session, sid)
    icon = await service_favicon.fetch_favicon(s, docker)
    if icon is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT,
                            f"Couldn't find an icon for {s.name}.")
    s.icon, s.icon_custom = icon, False
    session.add(s)
    await audit_request(session, request, "service.icon_refresh", user_id=admin.id,
                        resource=s.id)
    await session.commit()
    await session.refresh(s)
    return _out(s, await _preset_map(session))
