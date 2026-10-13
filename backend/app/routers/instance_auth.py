"""Traefik forwardAuth for instance desktops (/i/<sub>, extra ports) — spec §10.1.

Instance subdomains are user-chosen, so the route alone is no secret: every
instance router runs this check (Styx login via styx_proxy + owner-or-admin,
the same rule as /api/instances) and it also strips Styx cookies.

The instance comes from the forwardAuth address route_writer gives each
instance's routers (/internal/instances/<id>/auth-check), never from parsing
the request: Traefik's routing and our parsing can never disagree.
"""
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlmodel.ext.asyncio.session import AsyncSession

from app.database import get_session
from app.models import Instance
from app.routers.services_auth import login_redirect
from app.security.cookies import clean_cookie_header
from app.security.deps import proxy_user_or_none, require_owner_or_admin

internal_router = APIRouter()


@internal_router.get("/{instance_id}/auth-check")
async def auth_check(instance_id: str, request: Request,
                     session: AsyncSession = Depends(get_session)):
    user = await proxy_user_or_none(request, session)
    if user is None:
        # next= is only a convenience (re-validated by safe_next); host-routed
        # extra ports (<sub>.<domain>/p/…) mean nothing on the portal domain.
        uri = request.headers.get("x-forwarded-uri", "")
        return login_redirect(request, uri if uri.startswith("/i/") else None)
    inst = await session.get(Instance, instance_id)
    # 5xx → instance-unavailable-errors serves the same page instances_fallback does.
    if inst is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Instance unavailable")
    require_owner_or_admin(inst.owner_id, user)
    if inst.status not in ("running", "idle"):
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Instance unavailable")
    return Response(status_code=200, headers=clean_cookie_header(request))
