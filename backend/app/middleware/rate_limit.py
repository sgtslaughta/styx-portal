import ipaddress
import logging
import threading
import time
from collections import deque
from functools import lru_cache

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import Settings

_settings = Settings()
logger = logging.getLogger(__name__)
MAX_TRACKED = 100_000   # cap on the per-key hit map (oldest key evicted)


@lru_cache(maxsize=8)
def _trusted_networks(spec: str) -> tuple:
    return tuple(ipaddress.ip_network(c.strip(), strict=False)
                 for c in spec.split(",") if c.strip())


def own_subnets(path: str = "/proc/net/route") -> tuple:
    """IPv4 subnets of this host/container's own interfaces (stdlib, Linux only).

    Traefik shares a docker network with the backend, so it is always inside one of these,
    whatever pool docker picked. Default route (mask 0) is skipped; no file = empty.
    """
    nets = []
    try:
        with open(path) as f:
            rows = f.read().splitlines()[1:]
    except OSError:
        return ()
    for row in rows:
        cols = row.split()
        try:
            dest, mask = (int(cols[1], 16), int(cols[7], 16))
            if mask == 0:
                continue
            # kernel prints these little-endian
            dest, mask = (int.from_bytes(v.to_bytes(4, "big"), "little") for v in (dest, mask))
            nets.append(ipaddress.ip_network((dest, bin(mask).count("1")), strict=False))
        except (IndexError, ValueError):
            continue
    return tuple(nets)


# Frozen once at startup (lifespan), before any screenshot/background task can join an
# instance network: later-joined networks must never become trusted proxies.
_startup_networks: tuple = ()
_snapshot_taken = False


def snapshot_own_networks(path: str = "/proc/net/route") -> None:
    global _startup_networks, _snapshot_taken
    if not _snapshot_taken:
        _startup_networks, _snapshot_taken = own_subnets(path), True
        if not _startup_networks:
            logger.error("no network interfaces found at startup (/proc/net/route unreadable?); "
                         "only TRUSTED_PROXY_CIDRS are trusted proxies")


def _own_networks() -> tuple:
    return _startup_networks


def _peer_is_trusted_proxy(host: str | None) -> bool:
    try:
        ip = ipaddress.ip_address(host or "")
    except ValueError:
        return False
    return (any(ip in net for net in _trusted_networks(_settings.TRUSTED_PROXY_CIDRS))
            or any(ip in net for net in _own_networks()))


# k8s: cloudflared shares the pod CIDR with every other pod (and with SNAT'd LAN clients),
# so it is identified by its exact live pod IPs. The lookup runs in a background thread
# (stale-while-revalidate): a request never waits on the k8s API. No good set yet = empty
# (fail closed: CF-Connecting-IP ignored); on error the last good set is kept.
_POD_TTL, _POD_RETRY, _POD_TIMEOUT = 30, 5, 2
_pod_ips: set[str] = set()
_pod_next = 0.0                      # monotonic time the next refresh is due
_pod_thread: threading.Thread | None = None
_pod_lock = threading.Lock()


def _refresh_tunnel_pod_ips(spec: str) -> None:
    global _pod_ips, _pod_next
    from app.services.k8s_api import incluster_client
    ns, _, selector = spec.partition(":")
    try:
        _pod_ips = incluster_client().list_pod_ips(ns, selector, timeout=_POD_TIMEOUT)
        _pod_next = time.monotonic() + _POD_TTL
    except Exception as e:
        _pod_next = time.monotonic() + _POD_RETRY
        logger.warning("cloudflared pod lookup failed, keeping %d cached IPs: %s",
                       len(_pod_ips), e)


def _tunnel_pod_ips() -> set[str]:
    global _pod_thread
    spec = _settings.TUNNEL_PEER_K8S
    if spec and time.monotonic() >= _pod_next:
        with _pod_lock:
            if _pod_thread is None or not _pod_thread.is_alive():
                _pod_thread = threading.Thread(target=_refresh_tunnel_pod_ips, args=(spec,),
                                               name="tunnel-pod-ips", daemon=True)
                _pod_thread.start()
    return _pod_ips


def _is_tunnel_peer(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    if any(addr in n for n in _trusted_networks(_settings.TUNNEL_PEER_CIDRS)):
        return True
    return bool(_settings.TUNNEL_PEER_K8S) and str(addr) in _tunnel_pod_ips()


def _is_private(host: str) -> bool:
    try:
        return ipaddress.ip_address(host).is_private
    except ValueError:
        return False


_warned: dict[str, float] = {}


def _warn_unknown_proxy(peer: str) -> None:
    now = time.monotonic()
    if now - _warned.get(peer, -1e9) >= 600:
        _warned[peer] = now
        logger.error("request via unrecognised proxy %s; restart the backend or add it to "
                     "TRUSTED_PROXY_CIDRS", peer)


def client_ip_resolved(request) -> tuple[str, bool]:
    """Returns (ip, resolved). Resolve the real client IP behind a trusted proxy (Cloudflare/Traefik).

    Forwarded headers are only honoured when the direct socket peer is in
    TRUSTED_PROXY_CIDRS (Traefik on a docker bridge); anyone else reaching the
    backend directly gets their socket address. CF-Connecting-IP is only
    meaningful behind Cloudflare (tunnel mode); in direct mode it is
    client-controlled, so the left-most X-Forwarded-For hop (which Traefik
    rewrites, as it trusts no upstream forwarded headers) is used instead.
    """
    peer = request.client.host if request.client else "unknown"
    if not _peer_is_trusted_proxy(peer):
        if request.headers.get("x-forwarded-for") and _is_private(peer):
            # A private peer that forwards for someone is almost certainly a proxy we do not
            # know (snapshot empty/stale): do not pin every client on its address.
            _warn_unknown_proxy(peer)
            return peer, False
        return peer, True
    cf = request.headers.get("cf-connecting-ip")
    xff = request.headers.get("x-forwarded-for")
    # CF-Connecting-IP is only believed when the peer Traefik saw (the XFF entry it
    # appended: the last one) is in the tunnel subnet or is a live cloudflared pod (k8s);
    # Traefik passes the header through unchanged, so anyone reaching a published Traefik port could forge it.
    if (cf and xff and _settings.DEPLOY_MODE == "tunnel"
            and _is_tunnel_peer(xff.split(",")[-1].strip())):
        return cf.strip(), True
    if xff:
        return xff.split(",")[0].strip(), True
    return peer, False   # fell back to the proxy itself: the real client is unknown


def client_ip_from_headers(request) -> str:
    return client_ip_resolved(request)[0]




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
        # Unresolved (unrecognised proxy) is limited by the peer IP: fail closed, never open.
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
