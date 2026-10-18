import ipaddress
import logging
import time
from collections import deque
from datetime import datetime, timedelta, timezone

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.config import Settings
from app.models import BannedIP

_settings = Settings()
logger = logging.getLogger("styx-portal")

MAX_TRACKED = 100_000   # cap on in-memory per-key maps (oldest key evicted)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def ip_key(ip: str) -> str:
    """Ban/track key for an IP: IPv6 collapses to its /64 (one host owns the whole prefix)."""
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return ip
    if addr.version == 6 and addr.ipv4_mapped:
        return str(addr.ipv4_mapped)
    if addr.version == 6:
        return str(ipaddress.ip_network(f"{ip}/64", strict=False))
    return str(addr)


def _bounded_deque(d: dict, key: str) -> deque:
    q = d.get(key)
    if q is None:
        if len(d) >= MAX_TRACKED:
            d.pop(next(iter(d)))
        q = d[key] = deque()
    return q


class IpFailTracker:
    """In-memory per-IP failed-login counter over a sliding window.

    record() returns True exactly when an IP first reaches the threshold,
    signalling the caller to persist a ban. The IP's window is cleared on that
    event so it does not re-fire on every subsequent failure.
    """

    def __init__(self, threshold: int, window: int):
        self.threshold = threshold
        self.window = window
        self._hits: dict[str, deque] = {}

    def record(self, ip: str, now: float | None = None) -> bool:
        now = time.monotonic() if now is None else now
        key = ip_key(ip)
        q = _bounded_deque(self._hits, key)
        q.append(now)
        while q and q[0] <= now - self.window:
            q.popleft()
        if len(q) >= self.threshold:
            self._hits.pop(key, None)
            return True
        return False

    def reset(self) -> None:
        self._hits.clear()


class LoginLockout:
    """Per-(username, client IP) login lockout, in memory.

    Keyed on the pair so a stranger failing against the admin's username only locks
    their own address out, never the real user on another IP. Thresholds are passed
    per call so the live admin settings apply.
    """

    def __init__(self) -> None:
        self._fails: dict[str, deque] = {}
        self._locked: dict[str, float] = {}
        self._global: dict[str, deque] = {}    # username -> failure times, any IP
        self._last_check: dict[str, float] = {}

    @staticmethod
    def _key(username: str, ip: str) -> str:
        return f"{username.strip().lower()}|{ip_key(ip)}"

    def is_locked(self, username: str, ip: str, now: float | None = None) -> bool:
        now = time.monotonic() if now is None else now
        key = self._key(username, ip)
        until = self._locked.get(key)
        if until is None:
            return False
        if until <= now:
            del self._locked[key]
            return False
        return True

    def record_fail(self, username: str, ip: str, threshold: int, duration: int,
                    now: float | None = None) -> bool:
        """Count a failure; True when this failure trips the lock."""
        now = time.monotonic() if now is None else now
        key = self._key(username, ip)
        g = _bounded_deque(self._global, username.strip().lower())
        g.append(now)
        while g and g[0] <= now - duration:
            g.popleft()
        q = _bounded_deque(self._fails, key)
        q.append(now)
        while q and q[0] <= now - duration:
            q.popleft()
        if len(q) >= threshold:
            self._fails.pop(key, None)
            if len(self._locked) >= MAX_TRACKED:
                self._locked.pop(next(iter(self._locked)))
            self._locked[key] = now + duration
            return True
        return False

    def throttled(self, username: str, threshold: int, duration: int,
                  now: float | None = None) -> bool:
        """Distributed-guessing brake: once a username has `threshold` failures (any IP)
        in the window, allow one password check per 10 s. Never a hard lock."""
        now = time.monotonic() if now is None else now
        name = username.strip().lower()
        g = self._global.get(name)
        if g is None:
            return False
        while g and g[0] <= now - duration:
            g.popleft()
        if len(g) < threshold:
            return False
        last = self._last_check.get(name)
        if last is not None and now - last < 10:
            return True
        if len(self._last_check) >= MAX_TRACKED:
            self._last_check.pop(next(iter(self._last_check)))
        self._last_check[name] = now
        return False

    def clear(self, username: str, ip: str) -> None:
        key = self._key(username, ip)
        self._fails.pop(key, None)
        self._locked.pop(key, None)

    def clear_user(self, username: str) -> None:
        prefix = f"{username.strip().lower()}|"
        for d in (self._fails, self._locked):
            for k in [k for k in d if k.startswith(prefix)]:
                del d[k]
        self._global.pop(username.strip().lower(), None)
        self._last_check.pop(username.strip().lower(), None)

    def reset(self) -> None:
        self._fails.clear()
        self._locked.clear()
        self._global.clear()
        self._last_check.clear()


class BanCache:
    """In-memory snapshot of active IP bans, refreshed from the DB on a TTL.

    is_banned() is a dict lookup on the hot forward-auth path. invalidate()
    forces the next is_banned() to refresh — used right after writing a ban so
    it takes effect immediately.
    """

    def __init__(self, ttl: int):
        self.ttl = ttl
        self._bans: dict[str, datetime] = {}
        self._loaded_at: float | None = None

    def invalidate(self) -> None:
        self._loaded_at = None

    async def refresh(self, session: AsyncSession, now: datetime | None = None) -> None:
        now = now or _now()
        # Convert to naive datetime for comparison (SQLite stores as naive)
        now_naive = now.replace(tzinfo=None) if now.tzinfo else now
        result = await session.exec(select(BannedIP).where(BannedIP.expires_at > now_naive))
        self._bans = {ip_key(b.ip): b.expires_at for b in result.all()}

    async def is_banned(self, session: AsyncSession, ip: str,
                        now: datetime | None = None,
                        mono: float | None = None) -> bool:
        now = now or _now()
        mono = time.monotonic() if mono is None else mono
        if self._loaded_at is None or mono - self._loaded_at >= self.ttl:
            await self.refresh(session, now)
            self._loaded_at = mono
        exp = self._bans.get(ip_key(ip))
        # Convert to naive datetime for comparison (SQLite stores as naive)
        now_naive = now.replace(tzinfo=None) if now.tzinfo else now
        return exp is not None and exp > now_naive


async def ban_ip(session: AsyncSession, ip: str, reason: str, duration: int,
                 now: datetime | None = None) -> bool:
    """Persist a ban. Refuses (False) for loopback only: that is the local proxy itself
    (client IP not resolved), and banning it would lock everyone out."""
    ip = ip_key(ip)
    try:
        loopback = ipaddress.ip_address(ip).is_loopback
    except ValueError:
        loopback = False
    if loopback:
        logger.error("Refusing to ban loopback %s (client IP not resolved; check "
                     "DEPLOY_MODE / TRUSTED_PROXY_CIDRS). Reason: %s", ip, reason)
        return False
    now = now or _now()
    expires = now + timedelta(seconds=duration)
    existing = await session.get(BannedIP, ip)
    if existing:
        existing.reason = reason
        existing.banned_at = now
        existing.expires_at = expires
        session.add(existing)
    else:
        session.add(BannedIP(ip=ip, reason=reason, banned_at=now, expires_at=expires))
    return True


# Module singletons shared by the login flow and the ban-check endpoint.
fail_tracker = IpFailTracker(_settings.BAN_FAIL_THRESHOLD, _settings.BAN_FAIL_WINDOW)
ban_cache = BanCache(_settings.BAN_CACHE_TTL)
login_lockout = LoginLockout()
