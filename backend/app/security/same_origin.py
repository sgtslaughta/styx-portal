"""Mitigations for the single-origin design (proxied apps share Styx's origin).

Ceiling: JavaScript served by any proxied app still runs as its viewer. These two
checks only shut the cheap routes a malicious app would use against the Styx API
(docs/SERVICES.md, "Trust and same-origin apps").
"""
from urllib.parse import urlsplit

from fastapi import Depends, HTTPException, Request, status
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.database import get_session
from app.models import ProxiedService
from app.security.csrf import UNSAFE_METHODS
from app.services.service_routes import COOKIE_NAME, focus_slug, focus_value

# The only state changes the SPA and the Focus shell make while styx_svc is set.
_FOCUS_WRITE_OK = frozenset({"/api/auth/refresh", "/api/auth/logout", "/api/auth/me/preferences"})
_FOCUS_WRITE_PREFIX = "/api/services/focus"
# Referer paths that belong to a proxied app or stream, never to the Styx SPA.
_APP_PREFIXES = ("/i/", "/w/", "/_styx/app")


async def svc_cookie_guard(request: Request, session: AsyncSession = Depends(get_session)) -> None:
    """App-wide dependency: with a valid Focus cookie, /api writes are refused (403)
    except the allowlist. A stale/junk styx_svc value is not a Focus session."""
    path = request.url.path
    value = request.cookies.get(COOKIE_NAME)
    if (not value or request.method not in UNSAFE_METHODS or not path.startswith("/api")
            or path in _FOCUS_WRITE_OK or path.startswith(_FOCUS_WRITE_PREFIX)):
        return
    slug = focus_slug(value)
    if not slug:
        return
    svc = (await session.exec(select(ProxiedService).where(ProxiedService.slug == slug))).first()
    if svc and svc.mount_mode == "cookie-root" and value == focus_value(svc.slug, svc.id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not allowed while an app has focus")


async def require_spa_origin(request: Request, session: AsyncSession) -> None:
    """Admin writes from a browser must come from the Styx SPA, not a proxied app.

    Browsers always send Sec-Fetch-Dest; clients without it (curl, scripts) are not
    page scripts and are left to the CSRF check.
    """
    if request.method not in UNSAFE_METHODS:
        return
    dest = request.headers.get("sec-fetch-dest")
    if dest is None:
        return
    deny = HTTPException(status.HTTP_403_FORBIDDEN, "Admin changes must come from the Styx app")
    if dest != "empty":
        raise deny
    ref = request.headers.get("referer")
    if ref:
        path = urlsplit(ref).path or "/"
        if path.startswith(_APP_PREFIXES):
            raise deny
        first = path.split("/")[1] if path.count("/") else ""
        if first and (await session.exec(
                select(ProxiedService.id).where(ProxiedService.slug == first))).first():
            raise deny
        return
    origin = request.headers.get("origin")
    if not origin or urlsplit(origin).netloc != request.headers.get("host"):
        raise deny
