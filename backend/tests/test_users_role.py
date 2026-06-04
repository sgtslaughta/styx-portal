import pytest

from app.models import User
from app.security.passwords import hash_password


@pytest.mark.asyncio
async def test_promote_user_to_admin(admin_client, session):
    session.add(User(username="bob", password_hash=hash_password("x"),
                     role="user", is_active=True))
    await session.commit()
    uid = next(u["id"] for u in (await admin_client.get("/api/users")).json()
               if u["username"] == "bob")
    r = await admin_client.patch(f"/api/users/{uid}/role?role=admin")
    assert r.status_code == 200
    assert r.json()["role"] == "admin"


@pytest.mark.asyncio
async def test_demote_admin_when_another_exists(admin_client, session):
    session.add(User(username="admin2", password_hash=hash_password("x"),
                     role="admin", is_active=True))
    await session.commit()
    me = (await admin_client.get("/api/auth/me")).json()
    r = await admin_client.patch(f"/api/users/{me['id']}/role?role=user")
    assert r.status_code == 200
    assert r.json()["role"] == "user"


@pytest.mark.asyncio
async def test_cannot_demote_last_admin(admin_client):
    me = (await admin_client.get("/api/auth/me")).json()
    r = await admin_client.patch(f"/api/users/{me['id']}/role?role=user")
    assert r.status_code == 400
