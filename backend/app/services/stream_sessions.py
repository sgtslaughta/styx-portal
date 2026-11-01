"""Stream-session log: who streamed which workstation/instance, and for how long.

All functions add to the session but never commit (callers commit). Naive UTC datetimes
internally (SQLite returns naive)."""
from datetime import datetime, timedelta, timezone

from sqlmodel import delete, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import Instance, StreamSession, User, Workstation

RETENTION_DAYS = 400
REASONS = ("strict_nat", "firewall", "mobile", "unknown")


def _utc(now: datetime | None = None) -> datetime:
    n = now or datetime.now(timezone.utc)
    return n.astimezone(timezone.utc).replace(tzinfo=None) if n.tzinfo else n


async def _open_rows(session: AsyncSession, kind: str, target_id: str) -> list[StreamSession]:
    return list((await session.exec(select(StreamSession).where(
        StreamSession.target_kind == kind, StreamSession.target_id == target_id,
        StreamSession.ended_at.is_(None)))).all())


async def open_session(session: AsyncSession, kind: str, target_id: str, user_id: str | None,
                       now: datetime | None = None, **extra) -> StreamSession:
    """Open a session unless one is already open for this target+user (idempotent)."""
    rows = await _open_rows(session, kind, target_id)
    for r in rows:
        if r.user_id == user_id:
            return r
    row = StreamSession(target_kind=kind, target_id=target_id, user_id=user_id,
                        started_at=_utc(now), **extra)
    session.add(row)
    return row


async def close_session(session: AsyncSession, kind: str, target_id: str,
                        user_id: str | None = None, keep_user: bool = False,
                        now: datetime | None = None) -> int:
    """Close open sessions on a target. user_id given: only that user's (or, with
    keep_user, everyone except that user). No-op when nothing is open."""
    n = 0
    for r in await _open_rows(session, kind, target_id):
        if user_id is not None and ((r.user_id == user_id) == keep_user):
            continue
        r.ended_at = _utc(now)
        session.add(r)
        n += 1
    return n


async def sync_workstation(session: AsyncSession, ws: Workstation, now: datetime | None = None) -> None:
    """Align the log with the workstation's occupancy (call after heartbeat/release changes)."""
    if ws.occupied_by and (ws.active_connections or 0) > 0:
        await close_session(session, "workstation", ws.id, ws.occupied_by, keep_user=True, now=now)
        await open_session(session, "workstation", ws.id, ws.occupied_by, now)
    else:
        await close_session(session, "workstation", ws.id, now=now)


async def mark_relayed(session: AsyncSession, ws: Workstation, reason: str | None) -> None:
    """Flag the occupant's open session as relayed (relay bytes were reported)."""
    reason = reason if reason in REASONS else "unknown"
    for r in await _open_rows(session, "workstation", ws.id):
        if r.user_id == ws.occupied_by:
            r.relayed = True
            if reason != "unknown" or not r.relay_reason:
                r.relay_reason = reason
            session.add(r)


async def sync_instances(session: AsyncSession, now: datetime | None = None) -> None:
    """Instances stream while 'running'; idle/stopped/etc. close the session."""
    insts = (await session.exec(select(Instance))).all()
    for inst in insts:
        if inst.status == "running":
            await open_session(session, "instance", inst.id, inst.owner_id, now)
        else:
            await close_session(session, "instance", inst.id, now=now)


async def close_dangling(session: AsyncSession, older_than_s: int,
                         now: datetime | None = None) -> int:
    """Startup: close sessions left open across a restart (older than the offline threshold).
    Closed at the last time known active (workstation last_heartbeat, else started_at) so
    server downtime never counts as streaming time."""
    cutoff = _utc(now) - timedelta(seconds=older_than_s)
    rows = (await session.exec(select(StreamSession).where(
        StreamSession.ended_at.is_(None), StreamSession.started_at < cutoff))).all()
    for r in rows:
        end = r.started_at
        if r.target_kind == "workstation":
            ws = await session.get(Workstation, r.target_id)
            if ws and ws.last_heartbeat:
                end = max(end, min(_utc(ws.last_heartbeat), _utc(now)))
        r.ended_at = end
        session.add(r)
    return len(rows)


async def prune(session: AsyncSession, now: datetime | None = None) -> None:
    await session.exec(delete(StreamSession).where(
        StreamSession.started_at < _utc(now) - timedelta(days=RETENTION_DAYS)))


async def _clipped(session: AsyncSession, days: int, now: datetime | None):
    """Yield (row, hours) for each session overlapping the window, clipped to it."""
    end = _utc(now)
    start = end - timedelta(days=days)
    rows = (await session.exec(select(StreamSession).where(
        StreamSession.started_at < end,
        (StreamSession.ended_at.is_(None)) | (StreamSession.ended_at > start)))).all()
    for r in rows:
        a, b = max(r.started_at, start), min(r.ended_at or end, end)
        if b > a:
            yield r, (b - a).total_seconds() / 3600


async def streaming_hours(session: AsyncSession, days: int = 7, top: int = 5,
                          now: datetime | None = None) -> list[dict]:
    """[{workstation, sub, parts: {username: hours}}], largest `top` targets first
    (raw per-user parts; the frontend folds users into Others)."""
    by: dict[tuple[str, str], dict[str, float]] = {}
    async for r, h in _clipped(session, days, now):
        parts = by.setdefault((r.target_kind, r.target_id), {})
        parts[r.user_id or ""] = parts.get(r.user_id or "", 0) + h
    users = {u.id: u.username for u in (await session.exec(select(User))).all()}
    ws = {w.id: w for w in (await session.exec(select(Workstation))).all()}
    ins = {i.id: i for i in (await session.exec(select(Instance))).all()}
    rows = []
    for (kind, tid), parts in by.items():
        if kind == "workstation":
            w = ws.get(tid)
            name, sub = (w.name, w.hostname) if w else (tid, "")
        else:
            i = ins.get(tid)
            name, sub = (i.name, "instance") if i else (tid, "instance")
        rows.append({"workstation": name, "sub": sub,
                     "parts": {users.get(u, u or "unknown"): round(h, 2) for u, h in parts.items()}})
    rows.sort(key=lambda r: -sum(r["parts"].values()))
    return rows[:top] if top else rows


async def sessions_per_day(session: AsyncSession, days: int = 14,
                           now: datetime | None = None) -> list[dict]:
    end = _utc(now)
    first = (end - timedelta(days=days - 1)).replace(hour=0, minute=0, second=0, microsecond=0)
    counts = {(first + timedelta(days=i)).date().isoformat(): 0 for i in range(days)}
    for t in (await session.exec(select(StreamSession.started_at).where(
            StreamSession.started_at >= first))).all():
        k = t.date().isoformat()
        if k in counts:
            counts[k] += 1
    return [{"date": d, "count": c} for d, c in counts.items()]
