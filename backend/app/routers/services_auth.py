"""Traefik forwardAuth target, cookie-root enter/exit, unavailable page (spec §4.2, §5)."""
import posixpath
import re
from urllib.parse import quote, unquote

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.database import get_session
from app.models import ProxiedService, User
from app.routers.groups import user_group_names
from app.routers.workstations import _redirect_host
from app.security.deps import get_current_user, proxy_user_or_none
from app.services.service_routes import COOKIE_NAME

router = APIRouter()
# Mounted at /internal: no Traefik router matches it, so only Traefik's
# forwardAuth (backend:8000 on the docker network) can reach auth-check.
internal_router = APIRouter()
exit_router = APIRouter()
pages_router = APIRouter()

# Same-site absolute path only: one leading "/", then no "/", "\", whitespace or controls
# right after it ("//host" and "/\host" are protocol-relative to browsers).
_SAFE_NEXT = re.compile(r"^/(?![/\\])[A-Za-z0-9._~!$&'()*+,;=:@%/?#\[\]-]*$")


async def get_service_by_slug(session: AsyncSession, slug: str) -> ProxiedService | None:
    return (await session.exec(select(ProxiedService).where(ProxiedService.slug == slug))).first()


_ENCODED_SEP = re.compile(r"%(2e|2f|5c)", re.IGNORECASE)


def _bypass_path(uri: str) -> str | None:
    """Normalised request path, or None if it smells of traversal/encoding tricks.

    The upstream may decode or normalise differently than a string compare, so
    any encoded ".", "/", "\\", backslash or ".." segment (raw or decoded,
    which also catches double-encoding) disqualifies the request from bypass.
    """
    raw = uri.split("?", 1)[0].split("#", 1)[0]
    decoded = unquote(raw)
    for p in (raw, decoded):
        if "\\" in p or _ENCODED_SEP.search(p) or ".." in p.split("/"):
            return None
    if not decoded.startswith("/"):
        return None
    norm = re.sub(r"/+", "/", posixpath.normpath(decoded))
    if decoded.endswith("/") and norm != "/":
        norm += "/"
    return norm


def bypass_matches(rules: list[dict], uri: str, headers) -> bool:
    path = _bypass_path(uri)
    if path is None:
        return False
    for rule in rules:
        prefix = rule.get("path_prefix", "/")
        if not (path == prefix or path.startswith(prefix.rstrip("/") + "/")):
            continue
        hdr = rule.get("required_header")
        if not hdr or hdr.lower() in headers:
            return True
    return False


async def user_may_open(session: AsyncSession, user: User, svc: ProxiedService) -> bool:
    if user.role == "admin" or not svc.allowed_groups:
        return True
    names = await user_group_names(session, user.id)
    return bool(set(names) & set(svc.allowed_groups))


def _login_redirect(request: Request, uri: str, cookie_root: bool = False):
    is_nav = (request.headers.get("sec-fetch-mode") == "navigate"
              or "text/html" in request.headers.get("accept", ""))
    if not is_nav:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    proto = request.headers.get("x-forwarded-proto", "https")
    if proto not in ("http", "https"):
        proto = "https"
    login = "/login"
    if _SAFE_NEXT.match(uri):
        login += f"?next={quote(uri, safe='/?=&')}"
    if cookie_root:
        # While styx_svc is set, /login itself routes to the service: clear the
        # cookie first or the browser loops between the app and auth-check.
        login = f"/_styx/exit?next={quote(login, safe='')}"
    return RedirectResponse(f"{proto}://{_redirect_host(request)}{login}", status_code=302)


@internal_router.get("/services/{slug}/auth-check")
async def auth_check(slug: str, request: Request,
                     session: AsyncSession = Depends(get_session)):
    svc = await get_service_by_slug(session, slug)
    if svc is None or not svc.enabled:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown service")
    uri = request.headers.get("x-forwarded-uri", "/")
    if svc.auth_mode == "sso-with-bypass" and bypass_matches(svc.bypass_rules, uri, request.headers):
        return Response(status_code=200)
    user = await proxy_user_or_none(request, session)
    if user is None:
        return _login_redirect(request, uri, svc.mount_mode == "cookie-root")
    if not await user_may_open(session, user, svc):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "No access to this service")
    groups = await user_group_names(session, user.id)
    return Response(status_code=200,
                    headers={"X-Styx-User": user.username, "X-Styx-Groups": ",".join(groups)})


@router.post("/{slug}/enter")
async def enter_service(slug: str, user: User = Depends(get_current_user),
                        session: AsyncSession = Depends(get_session)):
    svc = await get_service_by_slug(session, slug)
    if svc is None or not svc.enabled:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown service")
    if svc.mount_mode != "cookie-root":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Service is not cookie-root mounted")
    if not await user_may_open(session, user, svc):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "No access to this service")
    resp = Response(status_code=200)
    resp.set_cookie(COOKIE_NAME, svc.slug, path="/", httponly=True, secure=True, samesite="lax")
    return resp


@exit_router.get("/exit")
async def exit_service(next: str = "/"):
    resp = RedirectResponse(next if _SAFE_NEXT.match(next) else "/", status_code=302)
    resp.delete_cookie(COOKIE_NAME, path="/")
    return resp


_UNAVAILABLE_HTML = """<!doctype html><html><head><meta charset="utf-8">
<title>Service unavailable</title>
<style>body{font-family:system-ui;background:#0b0f14;color:#e6edf3;display:grid;
place-items:center;height:100vh;margin:0}main{text-align:center}a{color:#7aa2f7}</style>
</head><body><main><h1>Service unavailable</h1>
<p>Styx could not reach this service. It may be stopped or still starting.</p>
<p><a href="/_styx/exit">Back to Styx</a></p></main></body></html>"""


@pages_router.get("/service-unavailable", include_in_schema=False)
async def service_unavailable():
    return HTMLResponse(_UNAVAILABLE_HTML, status_code=503)
