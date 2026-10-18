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
    """Per-(username, client IP) login lockout plus a per-username distributed brake.

    In memory. Only usernames that exist are tracked (the caller knows), which bounds the
    per-username maps by the user count. The (username, ip) maps are capped, but an active
    lock is never evicted: on a full map, expired entries go first, then the oldest
    non-locked failure counters. Thresholds are passed per call (live admin settings).
    """

    PURGE_EVERY = 60.0

    def __init__(self) -> None:
        self._fails: dict[str, deque] = {}
        self._locked: dict[str, float] = {}
        self._global: dict[str, deque] = {}    # username -> failure times, any IP
        self._last_check: dict[str, float] = {}
        self._last_purge = 0.0
        self._device_fails: dict[str, deque] = {}   # device-token rnd -> failure times
        self._device_blocked: dict[str, float] = {}

    @staticmethod
    def _key(username: str, ip: str) -> str:
        return f"{username.strip().lower()}|{ip_key(ip)}"

    def _purge(self, now: float, duration: int) -> None:
        for k in [k for k, u in self._locked.items() if u <= now]:
            del self._locked[k]
        for k in [k for k, u in self._device_blocked.items() if u <= now]:
            del self._device_blocked[k]
        for k in [k for k, q in self._device_fails.items() if not q or q[-1] <= now - duration]:
            del self._device_fails[k]
        for k in [k for k, q in self._fails.items() if not q or q[-1] <= now - duration]:
            del self._fails[k]
        self._last_purge = now

    def _fail_deque(self, key: str, now: float, duration: int,
                    store: dict | None = None) -> deque:
        store = self._fails if store is None else store
        q = store.get(key)
        if q is None:
            if len(store) >= MAX_TRACKED:
                if now - self._last_purge >= self.PURGE_EVERY:
                    self._purge(now, duration)
                if len(store) >= MAX_TRACKED:      # fail counters only, never blocks/locks
                    store.pop(next(iter(store)))
            q = store[key] = deque()
        return q

    # --- trusted-device tokens: each has its own failure budget -------------------
    def device_blocked(self, rnd: str, now: float | None = None) -> bool:
        now = time.monotonic() if now is None else now
        until = self._device_blocked.get(rnd)
        if until is None:
            return False
        if until <= now:
            del self._device_blocked[rnd]
            return False
        return True

    def device_fail(self, rnd: str, threshold: int, duration: int,
                    now: float | None = None) -> None:
        """Count a failed attempt made with this (validly signed) device token."""
        now = time.monotonic() if now is None else now
        q = self._fail_deque(rnd, now, duration, self._device_fails)
        q.append(now)
        while q and q[0] <= now - duration:
            q.popleft()
        if len(q) >= threshold:
            self._device_fails.pop(rnd, None)
            self._device_blocked[rnd] = now + duration

    def device_clear(self, rnd: str) -> None:
        self._device_fails.pop(rnd, None)
        self._device_blocked.pop(rnd, None)

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

    def locked_for(self, username: str, now: float | None = None) -> float:
        """Seconds until the longest active lock on this username (any IP) ends; 0 = none."""
        now = time.monotonic() if now is None else now
        prefix = f"{username.strip().lower()}|"
        return max([u - now for k, u in self._locked.items() if k.startswith(prefix)] + [0.0])

    def record_fail(self, username: str, ip: str, threshold: int, duration: int,
                    now: float | None = None) -> bool:
        """Count a failure; True when this failure trips the lock."""
        now = time.monotonic() if now is None else now
        key = self._key(username, ip)
        g = self._global.setdefault(username.strip().lower(), deque())
        g.append(now)
        while g and g[0] <= now - duration:
            g.popleft()
        q = self._fail_deque(key, now, duration)
        q.append(now)
        while q and q[0] <= now - duration:
            q.popleft()
        if len(q) >= threshold:
            self._fails.pop(key, None)
            self._locked[key] = now + duration
            return True
        return False

    def throttled(self, username: str, threshold: int, duration: int,
                  now: float | None = None) -> bool:
        """Distributed-guessing brake: once a username has `threshold` failures (any IP)
        in the window, allow one password check per 10 s. Never a hard lock; a trusted
        device cookie skips it."""
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
        self._device_fails.clear()
        self._device_blocked.clear()


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
    """Persist a ban (keyed by ip_key). Callers only pass resolved client IPs."""
    ip = ip_key(ip)
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
