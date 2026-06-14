from datetime import datetime, timezone, timedelta
from app.models import User
from app.security.passwords import hash_password


async def _mk(session, name="target"):
    u = User(username=name, password_hash=hash_password("x" * 12))
    session.add(u)
    await session.commit()
    return u


async def test_unlock_clears_lock(admin_client, session):
    u = await _mk(session)
    u.failed_count = 9
    u.locked_until = datetime.now(timezone.utc) + timedelta(minutes=5)
    session.add(u)
    await session.commit()
    r = await admin_client.post(f"/api/users/{u.id}/unlock")
    assert r.status_code == 200, r.text
    await session.refresh(u)
    assert u.failed_count == 0 and u.locked_until is None


async def test_unlock_requires_admin(client, session):
    u = await _mk(session, "t2")
    r = await client.post(f"/api/users/{u.id}/unlock")
    assert r.status_code in (401, 403)
