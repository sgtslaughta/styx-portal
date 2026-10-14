"""Traefik forwardAuth target, cookie-root enter/exit, unavailable page (spec §4.2, §5)."""
import html
import posixpath
import re
from urllib.parse import parse_qs, quote, unquote

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.database import get_session
from app.schemas_services import SERVICE_SLUG_RE
from app.models import ProxiedService, User
from app.routers.groups import user_group_names
from app.routers.workstations import _redirect_host
from app.config import Settings
from app.security.cookies import clean_cookie_header
from app.security.page_style import styx_page
from app.middleware.security_headers import SAMEORIGIN_HEADERS
from app.security.nav import is_navigation, no_access
from app.security.deps import get_current_user, proxy_user_or_none
from app.security.safe_next import safe_next
from app.services.service_routes import COOKIE_NAME

_settings = Settings()
router = APIRouter()
# Mounted at /internal: no Traefik router matches it, so only Traefik's
# forwardAuth (backend:8000 on the docker network) can reach auth-check.
internal_router = APIRouter()
exit_router = APIRouter()
pages_router = APIRouter()

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
        q = rule.get("required_query")
        if q:
            base = uri.split("#", 1)[0]
            qs = base.split("?", 1)[1] if "?" in base else ""
            vals = parse_qs(qs).get(q, [])
            if any(v.strip() for v in vals):
                return True
            continue
        hdr = rule.get("required_header")
        if not hdr:
            return True
        val = (headers.get(hdr.lower()) or "").strip()
        pre = rule.get("header_prefix")
        if val and (not pre or val.lower().startswith(pre.lower())):
            return True
    return False


async def user_may_open(session: AsyncSession, user: User, svc: ProxiedService) -> bool:
    if user.role == "admin" or not svc.allowed_groups:
        return True
    names = await user_group_names(session, user.id)
    return bool(set(names) & set(svc.allowed_groups))


def _shell_path(slug: str, uri: str | None, cookie_root: bool) -> str | None:
    """Where /_styx/app/ would show `uri` for this service (mirrors shellPathFor)."""
    if not uri or not uri.startswith("/"):
        return None
    if not cookie_root and uri != f"/{slug}" and not uri.startswith((f"/{slug}/", f"/{slug}?")):
        return None
    return f"/_styx/app{uri}" if not cookie_root else f"/_styx/app/{slug}{uri}"


def _expired_frame_page(login: str) -> HTMLResponse:
    # No inline script (CSP script-src 'self'): a plain link that breaks out of the frame.
    body = ("<h1>Your session expired</h1><p>Sign in again to keep using this app.</p>"
            f'<div class="actions"><a class="btn" target="_top" href="{html.escape(login)}">Sign in</a></div>')
    return HTMLResponse(styx_page("Session expired", body), status_code=401,
                        headers={"Cache-Control": "no-store", **SAMEORIGIN_HEADERS})


def login_redirect(request: Request, uri: str | None, cookie_root: bool = False,
                   shell_slug: str | None = None):
    """forwardAuth denial for an anonymous request: 302 to /login (next= only
    when safe_next allows it) for navigations, 401 for XHR/websocket. A navigation
    inside the shell's frame (shell_slug set) gets a small page instead, because
    /login cannot be framed: its link opens /login?next=<shell path> in the top window."""
    if not is_navigation(request):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    proto = request.headers.get("x-forwarded-proto", "https")
    if proto not in ("http", "https"):
        proto = "https"
    framed = shell_slug is not None and request.headers.get("sec-fetch-dest") in ("iframe", "frame")
    login = "/login"
    if framed:
        nxt = _shell_path(shell_slug, uri, cookie_root)
        if nxt and safe_next(nxt):
            login += f"?next={quote(nxt, safe='')}"
    elif safe_next(uri):
        login += f"?next={quote(uri, safe='/?=&')}"
    if cookie_root:
        # While styx_svc is set, /login itself routes to the service: clear the
        # cookie first or the browser loops between the app and auth-check.
        login = f"/_styx/exit?next={quote(login, safe='')}"
    if framed:
        return _expired_frame_page(login)
    return RedirectResponse(f"{proto}://{_redirect_host(request)}{login}", status_code=302)


@internal_router.get("/services/{slug}/auth-check")
async def auth_check(slug: str, request: Request,
                     session: AsyncSession = Depends(get_session)):
    svc = await get_service_by_slug(session, slug)
    if svc is None or not svc.enabled:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown service")
    uri = request.headers.get("x-forwarded-uri", "/")
    if svc.auth_mode == "sso-with-bypass" and bypass_matches(svc.bypass_rules, uri, request.headers):
        return Response(status_code=200, headers=clean_cookie_header(request))
    user = await proxy_user_or_none(request, session)
    if user is None:
        return login_redirect(request, uri, svc.mount_mode == "cookie-root", svc.slug)
    if not await user_may_open(session, user, svc):
        return no_access(request, "No access to this service")
    hdrs = clean_cookie_header(request)
    if svc.pass_identity:
        groups = await user_group_names(session, user.id)
        hdrs |= {"X-Styx-User": user.username, "X-Styx-Email": user.email or "",
                 "X-Styx-Groups": ",".join(groups)}
    return Response(status_code=200, headers=hdrs)


@internal_router.get("/strip")
@internal_router.get("/services/{slug}/strip")
async def strip_cookies(request: Request, slug: str | None = None):
    """Strip-only forwardAuth (app-native services): no auth,
    always 200 with the Cookie header minus Styx cookies."""
    return Response(status_code=200, headers=clean_cookie_header(request))


@router.get("/focus")
async def current_focus(request: Request, user: User = Depends(get_current_user)):
    return {"slug": request.cookies.get(COOKIE_NAME)}


@exit_router.get("/exit")
async def exit_service(next: str = "/"):
    resp = RedirectResponse(safe_next(next, allow_login=True) or "/", status_code=302)
    resp.delete_cookie(COOKIE_NAME, path="/")
    return resp


_CONFIRM_BODY = (
    "<h1>Open app?</h1><p>A link from another site wants to open <code>/{slug}</code> in Styx.</p>"
    '<div class="actions"><a class="btn" href="/_styx/open/{slug}">Open app</a><a href="/">Stay in Styx</a></div>')


def _focus_response(svc: ProxiedService) -> RedirectResponse:
    # frame_ok=False ("Open without overlay"): straight to the bare app at /
    resp = RedirectResponse(f"/_styx/app/{svc.slug}/" if svc.frame_ok else "/", status_code=302)
    resp.set_cookie(COOKIE_NAME, svc.slug, path="/", httponly=True,
                    secure=_settings.COOKIE_SECURE, samesite="lax")
    resp.headers["Clear-Site-Data"] = '"cache"'
    return resp


async def _open_target(slug: str, request: Request, session: AsyncSession):
    user = await proxy_user_or_none(request, session)
    if user is None:
        # No next: /_styx/open must never be a login next (it would skip the
        # confirm step). cookie_root clears any existing styx_svc first.
        return None, login_redirect(request, None, cookie_root=True)
    svc = await get_service_by_slug(session, slug)
    if svc is None or not svc.enabled or svc.mount_mode != "cookie-root":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown service")
    if not await user_may_open(session, user, svc):
        return None, no_access(request, "No access to this service")
    return svc, None


@exit_router.get("/open/{slug}")
async def open_service(slug: str, request: Request,
                       session: AsyncSession = Depends(get_session)):
    # Missing/other Sec-Fetch-Site = possibly cross-site: confirm page, no auth/DB.
    if request.headers.get("sec-fetch-site") not in ("same-origin", "none"):
        if not SERVICE_SLUG_RE.match(slug):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown service")
        return HTMLResponse(styx_page("Open app?", _CONFIRM_BODY.format(slug=html.escape(slug))),
                            headers={"Cache-Control": "no-store", **SAMEORIGIN_HEADERS})
    svc, deny = await _open_target(slug, request, session)
    return deny or _focus_response(svc)


_UNAVAILABLE_HTML = styx_page(
    "Service unavailable",
    "<h1>Service unavailable</h1><p>Styx could not reach this service. It may be stopped or "
    'still starting.</p><div class="actions"><a class="btn" href="/_styx/exit" target="_top">Back to Styx</a></div>')


@pages_router.get("/service-unavailable", include_in_schema=False)
async def service_unavailable():
    return HTMLResponse(_UNAVAILABLE_HTML, status_code=503, headers=SAMEORIGIN_HEADERS)
