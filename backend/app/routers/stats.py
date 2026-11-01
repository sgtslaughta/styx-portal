"""Admin stats for the Overview and Relay cost pages."""
import shutil
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.database import get_session
from app.models import StreamSession, User
from app.security.deps import require_admin
from app.services import cf_turn_usage, health_store, metric_rollup, stream_sessions, turn_usage
from app.services.settings_store import settings

router = APIRouter()
GB = 10 ** 9


def _slots(now: datetime) -> list[datetime]:
    cur = metric_rollup._hour(now)
    return [cur - timedelta(hours=i) for i in range(23, -1, -1)]


async def _series(session: AsyncSession, now: datetime):
    """24 hourly slots (oldest first): MetricHour rows + the in-progress hour."""
    by = {r.ts_hour: r for r in await metric_rollup.hour_rows(session, 2, now)}
    cur = metric_rollup.current_hour_values(now)
    out = []
    for h in _slots(now):
        v = by.get(h)
        if h == metric_rollup._hour(now) and cur:
            v = type("V", (), cur)
        out.append((h, v))
    return out


def _col(series, attr):
    return [None if v is None or getattr(v, attr) is None else round(getattr(v, attr), 1)
            for _, v in series]


async def _load(session: AsyncSession, series, rng: str, now: datetime) -> dict:
    if rng == "24h":
        return {"labels": [h.strftime("%H:00") for h, _ in series],
                "cpu": _col(series, "cpu_avg"), "ram": _col(series, "ram_avg")}
    days = 7 if rng == "7d" else 30
    daily: dict[str, list] = {}
    for r in await metric_rollup.hour_rows(session, days, now):
        daily.setdefault(r.ts_hour.date().isoformat(), []).append(r)
    labels = sorted(daily)
    def avg(rows, a):
        v = [getattr(r, a) for r in rows if getattr(r, a) is not None]
        return round(sum(v) / len(v), 1) if v else None
    return {"labels": labels, "cpu": [avg(daily[d], "cpu_avg") for d in labels],
            "ram": [avg(daily[d], "ram_avg") for d in labels]}


@router.get("/overview")
async def overview(range: Literal["24h", "7d", "30d"] = "24h",
                   admin: User = Depends(require_admin),
                   session: AsyncSession = Depends(get_session)):
    now = datetime.now(timezone.utc)
    series = await _series(session, now)
    host = metric_rollup.latest()
    d = shutil.disk_usage("/")
    live = len((await session.exec(select(StreamSession.id).where(
        StreamSession.ended_at.is_(None)))).all())
    last = lambda col: next((x for x in reversed(col) if x is not None), None)  # noqa: E731
    cpu, ram, disk, lv = (_col(series, a) for a in ("cpu_avg", "ram_avg", "disk_pct", "live_max"))
    health = [(v.health if v else None) for _, v in series]
    lvl = health_store.current_level()
    if lvl and (health[-1] is None or ("ok", "warn", "fail").index(lvl) > ("ok", "warn", "fail").index(health[-1])):
        health[-1] = lvl
    return {
        "tiles": {
            "cpu": {"now": host.get("cpu", last(cpu)), "series": cpu},
            "ram": {"now": host.get("ram", last(ram)), "series": ram},
            "disk": {"now": round(100 * (d.total - d.free) / d.total, 1), "series": disk},
            "live": {"now": live, "series": lv},
        },
        "health_hours": health,
        "load": await _load(session, series, range, now),
        "sessions_per_day": await stream_sessions.sessions_per_day(session, 14, now),
    }


@router.get("/streaming")
async def streaming(days: int = 7, top: int = 5, admin: User = Depends(require_admin),
                    session: AsyncSession = Depends(get_session)):
    days, top = max(1, min(days, 365)), max(0, min(top, 100))
    return {"rows": await stream_sessions.streaming_hours(session, days, top)}


def _gb(b: float) -> float:
    return round(b / GB, 3)


@router.get("/relay")
async def relay(period: Literal["this", "last", "6m"] = "this",
                admin: User = Depends(require_admin),
                session: AsyncSession = Depends(get_session)):
    if not cf_turn_usage.configured():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Relay cost tracking is not configured")
    now = datetime.now(timezone.utc)
    n = 6 if period == "6m" else 1
    months = turn_usage._months_back(now, n + 1 if period == "last" else n)
    if period == "last":
        months = months[:1]
    reports = [await turn_usage.usage_report(session, m, now) for m in months]
    used = sum(r["cf_egress_bytes"] if r["cf_egress_bytes"] is not None else r["total_bytes"]
               for r in reports)
    price, free, budget = (settings.get(k) for k in ("TURN_USD_PER_GB", "TURN_FREE_GB_MONTH", "TURN_BUDGET_GB"))
    agg = {"by_user": {}, "by_workstation": {}}
    for r in reports:
        for key, label in (("by_user", "username"), ("by_workstation", "name")):
            for x in r[key]:
                agg[key][x[label]] = agg[key].get(x[label], 0) + x["bytes"]
    reasons: dict[str, int] = {}
    for m in months:
        for x in await turn_usage.relay_reasons(session, m):
            reasons[x["reason"]] = reasons.get(x["reason"], 0) + x["sessions"]
    start = datetime(int(months[0][:4]), int(months[0][5:7]), 1)
    rows = (await session.exec(select(StreamSession.relayed).where(
        StreamSession.started_at >= start))).all()
    top = lambda d: [{"name": k, "gb": _gb(v)} for k, v in sorted(d.items(), key=lambda kv: -kv[1])]  # noqa: E731
    return {
        "used_gb": _gb(used), "free_gb": free * len(months),
        "projected_gb": _gb(reports[-1]["projected_bytes"]) if period == "this" else _gb(used),
        "est_usd": round(sum(r["est_usd"] for r in reports), 2),
        "budget_usd": round(max(0, budget - free) * float(price) * len(months), 2) if budget else 0.0,
        "relayed_pct": round(100 * sum(1 for x in rows if x) / len(rows), 1) if rows else 0.0,
        "daily": [{"date": x["date"], "gb": _gb(x["bytes"])} for x in await turn_usage.daily_bytes(session, 30, now)],
        "monthly": [{"month": x["month"], "gb": _gb(x["bytes"])} for x in await turn_usage.monthly_bytes(session, 6, now)],
        "by_user": top(agg["by_user"]), "by_workstation": top(agg["by_workstation"]),
        "reasons": [{"reason": k, "sessions": v} for k, v in sorted(reasons.items(), key=lambda kv: -kv[1])],
    }
