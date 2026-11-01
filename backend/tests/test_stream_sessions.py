from datetime import datetime, timedelta

from sqlmodel import select

from app.models import StreamSession, User, Workstation
from app.services import stream_sessions as ss
from app.services import turn_usage

NOW = datetime(2026, 10, 10, 12)


async def _ws(session):
    u = User(username="al", password_hash="x", role="member")
    session.add(u)
    await session.commit()
    w = Workstation(name="Box", hostname="box", subdomain="box", agent_token_hash="t",
                    created_by=u.id)
    session.add(w)
    await session.commit()
    return u, w


async def test_open_idempotent_and_close_noop(session):
    u, w = await _ws(session)
    a = await ss.open_session(session, "workstation", w.id, u.id, NOW)
    await session.commit()
    b = await ss.open_session(session, "workstation", w.id, u.id, NOW)
    assert a is b
    assert await ss.close_session(session, "workstation", w.id, now=NOW) == 1
    assert await ss.close_session(session, "workstation", w.id, now=NOW) == 0
    assert len((await session.exec(select(StreamSession))).all()) == 1


async def test_sync_workstation_handover(session):
    u, w = await _ws(session)
    w.occupied_by, w.active_connections = u.id, 1
    await ss.sync_workstation(session, w, NOW)
    await ss.sync_workstation(session, w, NOW)
    await session.commit()
    assert len((await session.exec(select(StreamSession))).all()) == 1
    w.active_connections = 0
    await ss.sync_workstation(session, w, NOW)
    await session.commit()
    assert (await session.exec(select(StreamSession))).one().ended_at is not None


async def test_streaming_hours_open_and_clipped(session):
    u, w = await _ws(session)
    session.add(StreamSession(target_kind="workstation", target_id=w.id, user_id=u.id,
                              started_at=NOW - timedelta(days=9), ended_at=NOW - timedelta(days=6, hours=12)))
    session.add(StreamSession(target_kind="workstation", target_id=w.id, user_id=u.id,
                              started_at=NOW - timedelta(hours=2)))   # open
    await session.commit()
    rows = await ss.streaming_hours(session, 7, now=NOW)
    # clipped: 12h inside window (day 7 -> 6.5) + open 2h
    assert rows == [{"workstation": "Box", "sub": "box", "parts": {"al": 14.0}}]


async def test_sessions_per_day_and_dangling(session):
    u, w = await _ws(session)
    session.add(StreamSession(target_kind="workstation", target_id=w.id, user_id=u.id,
                              started_at=NOW - timedelta(days=1)))
    await session.commit()
    days = await ss.sessions_per_day(session, 14, NOW)
    assert len(days) == 14 and days[-1]["date"] == "2026-10-10"
    assert days[-2] == {"date": "2026-10-09", "count": 1}
    assert await ss.close_dangling(session, 90, now=NOW) == 1
    assert await ss.close_dangling(session, 90, now=NOW) == 0


async def test_relay_reason_and_aggregates(session):
    u, w = await _ws(session)
    w.occupied_by, w.active_connections = u.id, 1
    await ss.sync_workstation(session, w)
    await ss.mark_relayed(session, w, "firewall")
    await turn_usage.record_turn_usage(session, w, 5 * 10 ** 6)
    await session.commit()
    month = datetime.now().strftime("%Y-%m")
    assert await turn_usage.relay_reasons(session, month) == [{"reason": "firewall", "sessions": 1}]
    d = await turn_usage.daily_bytes(session, 3)
    assert len(d) == 3 and d[-1]["bytes"] == 5 * 10 ** 6
    assert (await turn_usage.monthly_bytes(session, 6))[-1]["bytes"] == 5 * 10 ** 6


async def test_dangling_closed_at_last_heartbeat_not_now(session):
    u, w = await _ws(session)
    w.last_heartbeat = NOW - timedelta(hours=5)
    session.add(w)
    session.add(StreamSession(target_kind="workstation", target_id=w.id, user_id=u.id,
                              started_at=NOW - timedelta(hours=8)))
    session.add(StreamSession(target_kind="instance", target_id="i1", user_id=u.id,
                              started_at=NOW - timedelta(hours=3)))
    await session.commit()
    assert await ss.close_dangling(session, 90, now=NOW) == 2
    ends = {r.target_kind: r.ended_at for r in (await session.exec(select(StreamSession))).all()}
    assert ends["workstation"] == NOW - timedelta(hours=5)
    assert ends["instance"] == NOW - timedelta(hours=3)


async def test_sync_instances_open_close(session):
    from app.models import Instance, ServiceTemplate
    u, _ = await _ws(session)
    t = ServiceTemplate(name="t", display_name="T", image="img")
    session.add(t)
    await session.commit()
    i = Instance(template_id=t.id, owner_id=u.id, name="i", subdomain="i", status="running")
    session.add(i)
    await session.commit()
    await ss.sync_instances(session, NOW)
    await ss.sync_instances(session, NOW)
    await session.commit()
    rows = (await session.exec(select(StreamSession).where(StreamSession.target_kind == "instance"))).all()
    assert len(rows) == 1 and rows[0].ended_at is None and rows[0].user_id == u.id
    i.status = "idle"
    session.add(i)
    await ss.sync_instances(session, NOW)
    await session.commit()
    assert (await session.exec(select(StreamSession).where(StreamSession.target_kind == "instance"))).one().ended_at is not None
