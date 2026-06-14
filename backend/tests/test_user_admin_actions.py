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


async def test_reset_password_returns_temp_and_rotates(admin_client, session):
    from app.models import RefreshToken
    from app.security.passwords import verify_password
    u = await _mk(session, "resetme")
    session.add(RefreshToken(jti="j1", user_id=u.id, family_id="j1",
                             expires_at=datetime.now(timezone.utc) + timedelta(days=1)))
    await session.commit()
    r = await admin_client.post(f"/api/users/{u.id}/reset-password")
    assert r.status_code == 200, r.text
    temp = r.json()["temp_password"]
    assert len(temp) >= 12
    await session.refresh(u)
    assert u.must_change_pw is True
    assert verify_password(temp, u.password_hash)
    tok = await session.get(RefreshToken, "j1")
    assert tok.revoked is True


async def test_force_password_change(admin_client, session):
    u = await _mk(session, "forceme")
    r = await admin_client.post(f"/api/users/{u.id}/force-password-change")
    assert r.status_code == 200, r.text
    await session.refresh(u)
    assert u.must_change_pw is True
