"""Traefik forwardAuth for instance desktops (/i/<sub>, extra ports) — spec §10.1.

Instance subdomains are user-chosen, so the route alone is no secret: every
instance router runs this check (Styx login via styx_proxy + owner-or-admin,
the same rule as /api/instances) and it also strips Styx cookies.
"""
import re

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.config import Settings
from app.database import get_session
from app.models import Instance
from app.routers.services_auth import login_redirect
from app.security.cookies import clean_cookie_header
from app.security.deps import proxy_user_or_none, require_owner_or_admin

_settings = Settings()
internal_router = APIRouter()

_SUB = r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
_PATH_RE = re.compile(rf"^/i/({_SUB})(?:[/?#]|$)")   # /i/<sub>/…, /i/<sub>/p/<slug>/…
_DIRECT_PORT_RE = re.compile(r"^/p/[^/?#]+")          # direct mode: <sub>.<domain>/p/<slug>/…


def _subdomain(request: Request, uri: str) -> tuple[str | None, bool]:
    """(instance subdomain, routed by host?) from the forwarded request."""
    m = _PATH_RE.match(uri)
    if m:
        return m.group(1), False
    host = request.headers.get("x-forwarded-host", "").split(",")[0].strip().lower()
    host = re.sub(r":\d+$", "", host)
    suffix = "." + _settings.DOMAIN.lower()
    if _DIRECT_PORT_RE.match(uri) and host.endswith(suffix):
        sub = host[: -len(suffix)]
        if re.fullmatch(_SUB, sub):
            return sub, True
    return None, False


@internal_router.get("/auth-check")
async def auth_check(request: Request, session: AsyncSession = Depends(get_session)):
    uri = request.headers.get("x-forwarded-uri", "/")
    sub, by_host = _subdomain(request, uri)
    user = await proxy_user_or_none(request, session)
    if user is None:
        # Host-routed extra ports live on <sub>.<domain>; a /p/… next on the
        # portal domain would be meaningless, so log in without one.
        return login_redirect(request, None if by_host else uri)
    if sub is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Unknown instance path")
    inst = (await session.exec(select(Instance).where(Instance.subdomain == sub))).first()
    # 5xx → instance-unavailable-errors serves the same page instances_fallback does.
    if inst is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Instance unavailable")
    require_owner_or_admin(inst.owner_id, user)
    if inst.status not in ("running", "idle"):
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Instance unavailable")
    return Response(status_code=200, headers=clean_cookie_header(request))
