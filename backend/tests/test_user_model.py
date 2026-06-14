from app.models import User, Invite, Instance


def test_user_defaults():
    u = User(username="admin", password_hash="x")
    assert u.role == "user"
    assert u.is_active is True
    assert u.must_change_pw is False
    assert u.id


def test_invite_unused_by_default():
    inv = Invite(token_hash="abc", role="user", created_by="admin-id")
    assert inv.used_at is None


def test_instance_has_owner_field():
    inst = Instance(template_id="t", name="n", subdomain="s", owner_id="u1")
    assert inst.owner_id == "u1"


async def test_user_lockout_defaults(session):
    from app.models import User
    from app.security.passwords import hash_password
    u = User(username="lockme", password_hash=hash_password("x"))
    session.add(u)
    await session.commit()
    await session.refresh(u)
    assert u.failed_count == 0
    assert u.locked_until is None


async def test_banned_ip_roundtrip(session):
    from datetime import datetime, timezone, timedelta
    from app.models import BannedIP
    now = datetime.now(timezone.utc)
    session.add(BannedIP(ip="203.0.113.9", reason="test",
                         banned_at=now, expires_at=now + timedelta(hours=1)))
    await session.commit()
    got = await session.get(BannedIP, "203.0.113.9")
    assert got is not None
    assert got.reason == "test"
