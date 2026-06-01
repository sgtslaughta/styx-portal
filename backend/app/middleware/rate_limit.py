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


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, auth_spec: str, default_spec: str):
        super().__init__(app)
        self._auth = SlidingWindow(*_parse(auth_spec))
        self._default = SlidingWindow(*_parse(default_spec))

    async def dispatch(self, request: Request, call_next):
        ip = client_ip_from_headers(request)
        is_auth = request.url.path.startswith("/api/auth")
        window = self._auth if is_auth else self._default
        if not window.allow(f"{ip}:{is_auth}"):
            return JSONResponse(
                {"detail": "Too many requests"},
                status_code=429,
                headers={"Retry-After": str(window.window)},
            )
        return await call_next(request)
