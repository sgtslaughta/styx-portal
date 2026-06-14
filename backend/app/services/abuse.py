import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.config import Settings
from app.models import BannedIP

_settings = Settings()


def _now() -> datetime:
    return datetime.now(timezone.utc)


class IpFailTracker:
    """In-memory per-IP failed-login counter over a sliding window.

    record() returns True exactly when an IP first reaches the threshold,
    signalling the caller to persist a ban. The IP's window is cleared on that
    event so it does not re-fire on every subsequent failure.
    """

    def __init__(self, threshold: int, window: int):
        self.threshold = threshold
        self.window = window
        self._hits: dict[str, deque] = defaultdict(deque)

    def record(self, ip: str, now: float | None = None) -> bool:
        now = time.monotonic() if now is None else now
        q = self._hits[ip]
        q.append(now)
        while q and q[0] <= now - self.window:
            q.popleft()
        if len(q) >= self.threshold:
            q.clear()
            return True
        return False

    def reset(self) -> None:
        self._hits.clear()


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
        self._bans = {b.ip: b.expires_at for b in result.all()}

    async def is_banned(self, session: AsyncSession, ip: str,
                        now: datetime | None = None,
                        mono: float | None = None) -> bool:
        now = now or _now()
        mono = time.monotonic() if mono is None else mono
        if self._loaded_at is None or mono - self._loaded_at >= self.ttl:
            await self.refresh(session, now)
            self._loaded_at = mono
        exp = self._bans.get(ip)
        # Convert to naive datetime for comparison (SQLite stores as naive)
        now_naive = now.replace(tzinfo=None) if now.tzinfo else now
        return exp is not None and exp > now_naive


async def ban_ip(session: AsyncSession, ip: str, reason: str, duration: int,
                 now: datetime | None = None) -> None:
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


# Module singletons shared by the login flow and the ban-check endpoint.
fail_tracker = IpFailTracker(_settings.BAN_FAIL_THRESHOLD, _settings.BAN_FAIL_WINDOW)
ban_cache = BanCache(_settings.BAN_CACHE_TTL)
