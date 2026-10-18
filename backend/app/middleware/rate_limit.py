import ipaddress
import time
from collections import deque
from functools import lru_cache

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import Settings

_settings = Settings()
MAX_TRACKED = 100_000   # cap on the per-key hit map (oldest key evicted)


@lru_cache(maxsize=8)
def _trusted_networks(spec: str) -> tuple:
    return tuple(ipaddress.ip_network(c.strip(), strict=False)
                 for c in spec.split(",") if c.strip())


def _peer_is_trusted_proxy(host: str | None) -> bool:
    try:
        ip = ipaddress.ip_address(host or "")
    except ValueError:
        return False
    return any(ip in net for net in _trusted_networks(_settings.TRUSTED_PROXY_CIDRS))


def client_ip_from_headers(request) -> str:
    """Resolve the real client IP behind a trusted proxy (Cloudflare/Traefik).

    Forwarded headers are only honoured when the direct socket peer is in
    TRUSTED_PROXY_CIDRS (Traefik on a docker bridge); anyone else reaching the
    backend directly gets their socket address. CF-Connecting-IP is only
    meaningful behind Cloudflare (tunnel mode); in direct mode it is
    client-controlled, so the left-most X-Forwarded-For hop (which Traefik
    rewrites, as it trusts no upstream forwarded headers) is used instead.
    """
    peer = request.client.host if request.client else "unknown"
    if not _peer_is_trusted_proxy(peer):
        return peer
    cf = request.headers.get("cf-connecting-ip")
    if cf and _settings.DEPLOY_MODE == "tunnel":
        return cf.strip()
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return peer


class SlidingWindow:
    def __init__(self, limit: int, window: int):
        self.limit = limit
        self.window = window
        self._hits: dict[str, deque] = {}

    def allow(self, key: str, now: float | None = None) -> bool:
        now = time.monotonic() if now is None else now
        q = self._hits.get(key)
        if q is None:
            if len(self._hits) >= MAX_TRACKED:
                self._hits.pop(next(iter(self._hits)))
            q = self._hits[key] = deque()
        while q and q[0] <= now - self.window:
            q.popleft()
        if len(q) >= self.limit:
            return False
        q.append(now)
        return True


def _parse(spec: str) -> tuple[int, int]:
    limit, window = spec.split("/")
    return int(limit), int(window)


# Only credential-submitting POSTs get the strict brute-force bucket. The other
# /api/auth/* routes (setup-required, me, refresh, oauth/providers) are fired by
# the login page on every load and must use the lenient default bucket.
_STRICT_AUTH_PATHS = frozenset({
    "/api/auth/login",
    "/api/auth/accept-invite",
    "/api/auth/setup",
})


def is_strict_auth(method: str, path: str) -> bool:
    return method == "POST" and path in _STRICT_AUTH_PATHS


_EXEMPT_PATHS = frozenset({"/api/auth/ban-check"})


def is_rate_limit_exempt(path: str) -> bool:
    # /internal/: forwardAuth targets, already rate-limited by Traefik upstream.
    return path in _EXEMPT_PATHS or path.startswith("/internal/")


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app):
        super().__init__(app)
        self._windows: dict[str, SlidingWindow] = {}

    def _window_for(self, spec: str) -> SlidingWindow:
        w = self._windows.get(spec)
        if w is None:
            w = SlidingWindow(*_parse(spec))
            self._windows[spec] = w
        return w

    async def dispatch(self, request: Request, call_next):
        if is_rate_limit_exempt(request.url.path):
            return await call_next(request)
        from app.services.settings_store import settings
        ip = client_ip_from_headers(request)
        strict = is_strict_auth(request.method, request.url.path)
        spec = settings.get("RATE_LIMIT_AUTH") if strict else settings.get("RATE_LIMIT_DEFAULT")
        window = self._window_for(spec)
        if not window.allow(f"{ip}:{strict}"):
            return JSONResponse(
                {"detail": "Too many requests"},
                status_code=429,
                headers={"Retry-After": str(window.window)},
            )
        return await call_next(request)
