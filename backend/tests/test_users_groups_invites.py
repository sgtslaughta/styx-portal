import hashlib
from datetime import datetime, timedelta, timezone

import pytest

from app.models import Group, Invite, User, UserGroup
from app.security.passwords import hash_password


@pytest.mark.asyncio
async def test_list_users_includes_group_names(admin_client, session):
    u = User(username="bob", password_hash=hash_password("x"), role="user", is_active=True)
    g1, g2 = Group(name="media"), Group(name="family")
    session.add_all([u, g1, g2])
    await session.commit()
    session.add_all([UserGroup(user_id=u.id, group_id=g1.id), UserGroup(user_id=u.id, group_id=g2.id)])
    await session.commit()
    rows = {r["username"]: r for r in (await admin_client.get("/api/users")).json()}
    assert rows["bob"]["groups"] == ["family", "media"]


@pytest.mark.asyncio
async def test_list_invites_pending_only(admin_client, session):
    me = (await admin_client.get("/api/auth/me")).json()
    now = datetime.now(timezone.utc)

    def inv(tag, **kw):
        return Invite(token_hash=hashlib.sha256(tag.encode()).hexdigest(), created_by=me["id"], **kw)
    session.add_all([
        inv("a", email="a@x.io", expires_at=now + timedelta(hours=5)),
        inv("b", email="used@x.io", expires_at=now + timedelta(hours=5), used_at=now),
        inv("c", email="old@x.io", expires_at=now - timedelta(hours=1)),
    ])
    await session.commit()
    r = await admin_client.get("/api/users/invites")
    assert r.status_code == 200
    assert [i["email"] for i in r.json()] == ["a@x.io"]
