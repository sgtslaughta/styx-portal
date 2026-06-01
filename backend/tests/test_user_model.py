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
