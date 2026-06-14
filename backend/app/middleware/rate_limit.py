import time
from collections import defaultdict, deque

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware


def client_ip_from_headers(request) -> str:
    """Resolve the real client IP behind a trusted proxy (Cloudflare/Traefik).

    Backend is only reachable via the proxy, so these headers are trustworthy here.
    Prefers Cloudflare's CF-Connecting-IP, then the left-most X-Forwarded-For hop,
    then the direct socket peer.
    """
    cf = request.headers.get("cf-connecting-ip")
    if cf:
        return cf.strip()
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


class SlidingWindow:
    def __init__(self, limit: int, window: int):
        self.limit = limit
        self.window = window
        self._hits: dict[str, deque] = defaultdict(deque)

    def allow(self, key: str, now: float | None = None) -> bool:
        now = time.monotonic() if now is None else now
        q = self._hits[key]
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
    return path in _EXEMPT_PATHS


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
