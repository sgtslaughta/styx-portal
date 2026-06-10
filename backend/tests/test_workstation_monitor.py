import pytest
from datetime import datetime, timedelta, timezone

from app.models import User, Workstation
from app.security.passwords import hash_password
from app.services.workstations import mark_stale_offline


async def _ws(session, *, hb_age_s: int | None, status="online"):
    admin = User(username=f"a{hb_age_s}", password_hash=hash_password("x"), role="admin")
    session.add(admin)
    await session.commit()
    hb = (datetime.now(timezone.utc) - timedelta(seconds=hb_age_s)
          if hb_age_s is not None else None)
    ws = Workstation(name="w", subdomain=f"w{hb_age_s}", status=status,
                     last_heartbeat=hb, created_by=admin.id)
    session.add(ws)
    await session.commit()
    return ws


@pytest.mark.asyncio
async def test_stale_heartbeat_goes_offline(session):
    ws = await _ws(session, hb_age_s=300)
    assert await mark_stale_offline(session) is True
    assert ws.status == "offline"


@pytest.mark.asyncio
async def test_fresh_heartbeat_stays_online(session):
    ws = await _ws(session, hb_age_s=10)
    assert await mark_stale_offline(session) is False
    assert ws.status == "online"


@pytest.mark.asyncio
async def test_missing_heartbeat_goes_offline(session):
    ws = await _ws(session, hb_age_s=None)
    assert await mark_stale_offline(session) is True
    assert ws.status == "offline"
