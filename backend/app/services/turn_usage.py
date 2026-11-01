"""TURN relay usage metering (heartbeat deltas) and the admin cost estimate."""
import calendar
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import TurnUsage, User, Workstation
from app.services import cf_turn_usage
from app.services.settings_store import settings

GB = 10 ** 9


def _month(now: datetime) -> str:
    return now.strftime("%Y-%m")


async def record_turn_usage(session: AsyncSession, ws: Workstation, delta: Any,
                            now: datetime | None = None) -> None:
    """Add a heartbeat's relayed-byte delta to (month, workstation, occupant). Caller commits.

    NULL user_id rows never match `==` in SQL uniqueness/lookup, so use is_(None)."""
    if isinstance(delta, bool) or not isinstance(delta, int) or delta <= 0:
        return
    month = _month(now or datetime.now(timezone.utc))
    uid = ws.occupied_by
    cond = TurnUsage.user_id.is_(None) if uid is None else TurnUsage.user_id == uid
    row = (await session.exec(select(TurnUsage).where(
        TurnUsage.month == month, TurnUsage.workstation_id == ws.id, cond))).first()
    if row:
        row.bytes += delta
    else:
        row = TurnUsage(month=month, workstation_id=ws.id, user_id=uid, bytes=delta)
    session.add(row)


async def month_bytes(session: AsyncSession, now: datetime | None = None) -> int:
    month = _month(now or datetime.now(timezone.utc))
    rows = (await session.exec(select(TurnUsage.bytes).where(TurnUsage.month == month))).all()
    return int(sum(rows))


async def turn_over_budget(session: AsyncSession, now: datetime | None = None) -> bool:
    """Cost control: this month's relayed total has reached TURN_BUDGET_GB (0 = off)."""
    budget = settings.get("TURN_BUDGET_GB")
    if not budget:
        return False
    cf = (await cf_turn_usage.month_egress(now))["bytes"] or 0    # actual, when configured
    return max(await month_bytes(session, now), cf) >= budget * GB


def _money(x: Decimal) -> float:
    return float(round(x, 2))


async def usage_report(session: AsyncSession, month: str | None = None,
                       now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    cur = _month(now)
    month = month or cur
    rows = (await session.exec(select(TurnUsage).where(TurnUsage.month == month))).all()
    total = sum(r.bytes for r in rows)
    cf = await cf_turn_usage.month_egress(now) if month == cur else {"bytes": None, "error": None}
    free_gb = settings.get("TURN_FREE_GB_MONTH")
    try:
        price = Decimal(str(settings.get("TURN_USD_PER_GB")))
    except InvalidOperation:
        price = Decimal(0)

    def usd(b: int) -> float:
        over = max(Decimal(0), Decimal(b) / GB - free_gb)
        return _money(over * price)

    projected = total
    if month == cur:
        days = calendar.monthrange(now.year, now.month)[1]
        elapsed = (now.day - 1) + (now.hour * 3600 + now.minute * 60 + now.second) / 86400
        projected = int(total * days / max(elapsed, 1 / 24))   # floor at 1h: avoid blow-up on day 1
    by_ws: dict[str, int] = {}
    by_user: dict[str, int] = {}
    for r in rows:
        by_ws[r.workstation_id] = by_ws.get(r.workstation_id, 0) + r.bytes
        if r.user_id:
            by_user[r.user_id] = by_user.get(r.user_id, 0) + r.bytes
    names = {w.id: w.name for w in (await session.exec(select(Workstation))).all()}
    users = {u.id: u.username for u in (await session.exec(select(User))).all()}
    return {
        "month": month, "free_gb": free_gb, "usd_per_gb": float(price),
        "budget_gb": settings.get("TURN_BUDGET_GB"),
        "over_budget": month == cur and await turn_over_budget(session, now),
        "cf_egress_bytes": cf["bytes"], "cf_error": cf["error"],
        "total_bytes": total, "est_usd": usd(total),
        "projected_bytes": projected, "projected_usd": usd(projected),
        "by_workstation": [{"id": i, "name": names.get(i, i), "bytes": b}
                           for i, b in sorted(by_ws.items(), key=lambda kv: -kv[1])],
        "by_user": [{"id": i, "username": users.get(i, i), "bytes": b}
                    for i, b in sorted(by_user.items(), key=lambda kv: -kv[1])],
    }
