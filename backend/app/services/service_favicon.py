"""Fetch a proxied app's own favicon once, validated with the workstation-icon rules."""
import asyncio
import base64
import logging
import re
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

import httpx
from sqlmodel import update

from app.config import Settings
from app.models import ProxiedService, upstream_base
from app.services import ws_icon
from app.services.service_health import _forbidden_target

log = logging.getLogger(__name__)
PAGE_CAP = 512 * 1024
TIMEOUT = 5.0
MAX_CANDIDATES = 6
MAX_REDIRECTS = 3
_ICON_RELS = {"icon", "apple-touch-icon", "apple-touch-icon-precomposed"}
_DEFAULT_PORT = {"http": 80, "https": 443}


class _IconLinks(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links: list[dict] = []

    def handle_starttag(self, tag, attrs):
        if tag != "link":
            return
        a = {k: (v or "") for k, v in attrs}
        if _ICON_RELS & set(a.get("rel", "").lower().split()) and a.get("href", "").strip():
            self.links.append(a)


def _origin(url: str):
    p = urlsplit(url)
    try:
        return p.scheme, p.hostname, p.port or _DEFAULT_PORT.get(p.scheme)
    except ValueError:
        return None


def same_origin(a: str, b: str) -> bool:
    oa = _origin(a)
    return oa is not None and oa[0] in _DEFAULT_PORT and oa == _origin(b)


def _size(sizes: str) -> int:
    if sizes.strip().lower() == "any":
        return 1 << 30
    best = 0
    for m in re.finditer(r"(\d+)x(\d+)", sizes.lower()):
        best = max(best, int(m.group(1)))
    return best


def _rank(a: dict) -> tuple[int, int]:
    href = a["href"].split("?")[0].split("#")[0].lower()
    if a.get("type", "").lower() == "image/svg+xml" or href.endswith(".svg"):
        return 0, 0
    if "icon" not in a.get("rel", "").lower().split():
        return 2, -_size(a.get("sizes", ""))
    if a.get("type", "").lower() == "image/png" or href.endswith(".png"):
        return 1, -_size(a.get("sizes", ""))
    return 3, 0


def candidates(html: str, page_url: str) -> list[str]:
    """Icon URLs to try, best first: svg, largest png, apple-touch, other, /favicon.ico.

    Only same-origin URLs and data: URIs survive; the page can't point us elsewhere.
    """
    parser = _IconLinks()
    try:
        parser.feed(html)
    except Exception:  # noqa: BLE001 - html.parser may choke on garbage: use what we have
        log.debug("favicon html parse stopped early", exc_info=True)
    out: list[str] = []
    for a in sorted(parser.links, key=_rank):    # stable: document order within a rank
        href = a["href"].strip()
        url = href if href.lower().startswith("data:") else urljoin(page_url, href)
        if (url.startswith("data:") or same_origin(url, page_url)) and url not in out:
            out.append(url)
    ico = urljoin(page_url, "/favicon.ico")
    if ico not in out:
        out.append(ico)
    return out[:MAX_CANDIDATES]


def page_url(svc: ProxiedService) -> str:
    base = upstream_base(svc)
    return f"{base}/{svc.slug}/" if svc.mount_mode == "path" else f"{base}/"


async def _get_httpx(url: str, cap: int, verify: bool, origin_of: str,
                     transport: httpx.AsyncBaseTransport | None) -> bytes | None:
    """GET with a streamed body cap; redirects are followed only inside the original origin."""
    # verify=False is the per-service admin opt-in (verify_tls toggle).
    async with httpx.AsyncClient(verify=verify, timeout=TIMEOUT,  # nosec B501
                                 follow_redirects=False, transport=transport) as c:
        for _ in range(MAX_REDIRECTS + 1):
            if not same_origin(url, origin_of) or await _forbidden_target(url):
                return None
            async with c.stream("GET", url) as r:
                if r.is_redirect:
                    url = urljoin(url, r.headers.get("location", ""))
                    continue
                if r.status_code >= 400:
                    return None
                buf = bytearray()
                async for chunk in r.aiter_bytes():
                    buf += chunk
                    if len(buf) > cap:
                        break
                return bytes(buf[:cap]) or None
    return None


def _getter(svc: ProxiedService, docker, transport):
    if svc.kind == "docker-local":
        hosts = {"host.docker.internal": "host-gateway"} if svc.upstream_fallback else None

        async def get(url: str, cap: int) -> bytes | None:
            return await asyncio.to_thread(docker.probe_fetch, url, Settings().SERVICES_NETWORK,
                                           cap, extra_hosts=hosts)
        return get

    async def get(url: str, cap: int) -> bytes | None:
        return await _get_httpx(url, cap, svc.verify_tls, page_url(svc), transport)
    return get


def _validate(data: bytes) -> str | None:
    # validate_icon sniffs the real type; the declared mime here is only a placeholder.
    uri = f"data:image/x-unknown;base64,{base64.b64encode(data).decode()}"
    try:
        return ws_icon.validate_icon("image", uri)
    except ValueError:
        return None


async def fetch_favicon(svc: ProxiedService, docker, transport=None) -> str | None:
    """A validated icon data URI for the service, or None. Never raises."""
    try:
        get = _getter(svc, docker, transport)
        url = page_url(svc)
        page = await get(url, PAGE_CAP)
        html = page.decode("utf-8", "replace") if page else ""
        for cand in candidates(html, url):
            try:
                if cand.startswith("data:"):
                    m = re.match(r"data:[^;,]*;base64,(.*)$", cand, re.S)
                    data = base64.b64decode(m.group(1), validate=True) if m else None
                else:
                    data = await get(cand, ws_icon.MAX_IMAGE_BYTES + 1)
            except Exception:  # noqa: BLE001 - bad candidate: try the next
                log.debug("favicon candidate %s failed", cand[:80], exc_info=True)
                continue
            if data and (icon := _validate(data)):
                return icon
    except Exception:  # noqa: BLE001 - a favicon is never worth an error
        log.warning("favicon fetch for %s failed", svc.slug, exc_info=True)
    return None


def normalise_icon(value: str | None) -> str | None:
    """Request icon -> stored form. Bare emoji (presets), "emoji:<c>" or a data: image; else ValueError."""
    if not value:
        return None
    if value.startswith("data:"):
        return ws_icon.validate_icon("image", value)
    return ws_icon.validate_icon("emoji", value.removeprefix("emoji:"))


_tasks: set[asyncio.Task] = set()


def schedule_favicon(svc_id: str, docker) -> None:
    """Fire-and-forget fetch_and_store on the app's own DB sessions."""
    from app.database import async_session
    t = asyncio.create_task(fetch_and_store(async_session, svc_id, docker))
    _tasks.add(t)
    t.add_done_callback(_tasks.discard)


async def fetch_and_store(session_factory, svc_id: str, docker) -> None:
    """Background job: fetch for a non-custom service and store it (skipped if it became custom)."""
    try:
        async with session_factory() as s:
            svc = await s.get(ProxiedService, svc_id)
            if svc is None or svc.icon_custom:
                return
            snap = ProxiedService(**svc.model_dump())     # plain copy: no ORM row across awaits
        icon = await fetch_favicon(snap, docker)
        if icon is None:
            return
        async with session_factory() as s:
            await s.exec(update(ProxiedService).where(
                ProxiedService.id == svc_id, ProxiedService.icon_custom == False  # noqa: E712
            ).values(icon=icon))
            await s.commit()
    except Exception:  # noqa: BLE001
        log.warning("favicon store for %s failed", svc_id, exc_info=True)
