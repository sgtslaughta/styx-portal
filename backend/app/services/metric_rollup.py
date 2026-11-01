"""Host metric samples -> hourly MetricHour rows (90-day retention)."""
from datetime import datetime, timedelta, timezone
from threading import Lock

from sqlmodel import delete, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import MetricHour
from app.services import health_store

RETENTION_DAYS = 90
_RANK = {"ok": 0, "warn": 1, "fail": 2}
_lock = Lock()
_pending: list[dict] = []     # unflushed samples (30s cadence, ~120/hour)
_latest: dict = {}            # last host reading, for /api/system/metrics


def _naive(ts: datetime) -> datetime:
    return ts.astimezone(timezone.utc).replace(tzinfo=None) if ts.tzinfo else ts


def _hour(ts: datetime) -> datetime:
    return _naive(ts).replace(minute=0, second=0, microsecond=0)


def reset() -> None:
    with _lock:
        _pending.clear()
        _latest.clear()


def latest() -> dict:
    with _lock:
        return dict(_latest)


def record_host(cpu: float | None, ram: float | None, disk: float = 0, live: int = 0,
                ts: datetime | None = None, health: str | None = None) -> None:
    ts = _naive(ts or datetime.now(timezone.utc))
    if cpu is None and ram is None:
        return
    s = {"ts": ts, "cpu": cpu, "ram": ram, "disk": disk, "live": live,
         "health": health or health_store.current_level()}
    with _lock:
        _pending.append(s)
        _latest.update(cpu=cpu, ram=ram)


def _fold(samples: list[dict]) -> dict:
    cpus = [s["cpu"] for s in samples if s["cpu"] is not None]
    rams = [s["ram"] for s in samples if s["ram"] is not None]
    return {
        "cpu_avg": sum(cpus) / len(cpus) if cpus else 0, "cpu_max": max(cpus, default=0),
        "ram_avg": sum(rams) / len(rams) if rams else 0,
        "disk_pct": samples[-1]["disk"], "live_max": max(s["live"] for s in samples),
        "health": max((s["health"] for s in samples), key=_RANK.get),
    }


def current_hour_values(now: datetime | None = None) -> dict | None:
    """Fold of the in-progress hour's unflushed samples (None if none)."""
    h = _hour(now or datetime.now(timezone.utc))
    with _lock:
        cur = [s for s in _pending if _hour(s["ts"]) == h]
    return _fold(cur) if cur else None


async def rollup(session: AsyncSession, now: datetime | None = None, force: bool = False) -> int:
    """Flush samples of completed hours (all of them with force) into MetricHour, prune
    old rows, commit. Returns hours written. A row that already exists (restart mid-hour)
    is averaged with the new fold."""
    now = _naive(now or datetime.now(timezone.utc))
    cur = _hour(now)
    with _lock:
        take = [s for s in _pending if force or _hour(s["ts"]) < cur]
        _pending[:] = [s for s in _pending if s not in take]
    by: dict[datetime, list[dict]] = {}
    for s in take:
        by.setdefault(_hour(s["ts"]), []).append(s)
    for h, samples in by.items():
        v = _fold(samples)
        row = await session.get(MetricHour, h)
        if row is None:
            session.add(MetricHour(ts_hour=h, **v))
            continue
        row.cpu_avg, row.ram_avg = (row.cpu_avg + v["cpu_avg"]) / 2, (row.ram_avg + v["ram_avg"]) / 2
        row.cpu_max, row.live_max = max(row.cpu_max, v["cpu_max"]), max(row.live_max, v["live_max"])
        row.disk_pct = v["disk_pct"]
        row.health = max(row.health, v["health"], key=_RANK.get)
        session.add(row)
    await session.exec(delete(MetricHour).where(
        MetricHour.ts_hour < cur - timedelta(days=RETENTION_DAYS)))
    await session.commit()
    return len(by)


async def hour_rows(session: AsyncSession, days: int, now: datetime | None = None) -> list[MetricHour]:
    since = _hour(now or datetime.now(timezone.utc)) - timedelta(days=days)
    return list((await session.exec(select(MetricHour).where(
        MetricHour.ts_hour >= since).order_by(MetricHour.ts_hour))).all())
