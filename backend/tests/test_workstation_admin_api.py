import pytest
from httpx import ASGITransport, AsyncClient
from sqlmodel import select

from app.main import app
from app.models import User, Workstation, WorkstationAccess
from app.security.crypto import encrypt_secret
from app.security.passwords import hash_password


async def _seed(session):
    admin = (await session.exec(select(User).where(User.role == "admin"))).first()
    if admin is None:
        admin = User(username="admin", password_hash=hash_password("admin-password"), role="admin")
        session.add(admin)
        await session.commit()
    user = User(username="carol", password_hash=hash_password("x"), role="user")
    session.add(user)
    await session.commit()
    ws = Workstation(name="desk", subdomain="desk", hostname="desk",
                     lan_ip="192.168.1.50", status="online",
                     selkies_password_enc=encrypt_secret("pw123"),
                     created_by=admin.id)
    session.add(ws)
    await session.commit()
    await session.refresh(ws)
    return ws, user


@pytest.mark.asyncio
async def test_list_admin_only(admin_client, session):
    ws, _ = await _seed(session)
    # Create a fresh unauthenticated client for the first check
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as fresh_client:
        r = await fresh_client.get("/api/workstations")
        assert r.status_code == 401
    # Admin client can list
    r = await admin_client.get("/api/workstations")
    assert r.status_code == 200
    assert r.json()[0]["subdomain"] == "desk"


@pytest.mark.asyncio
async def test_patch_settings_and_access(admin_client, session):
    ws, user = await _seed(session)
    r = await admin_client.patch(f"/api/workstations/{ws.id}", json={
        "name": "Gaming rig", "stream_settings": {"encoder": "nvh264enc",
                                                  "framerate": 120,
                                                  "bitrate_kbps": 40000}})
    assert r.status_code == 200
    assert r.json()["stream_settings"]["framerate"] == 120
    r = await admin_client.put(f"/api/workstations/{ws.id}/access",
                               json={"user_ids": [user.id]})
    assert r.status_code == 200
    assert r.json()["allowed_user_ids"] == [user.id]


@pytest.mark.asyncio
async def test_delete_revokes_then_purges(admin_client, session):
    ws, _ = await _seed(session)
    r = await admin_client.delete(f"/api/workstations/{ws.id}")
    assert r.status_code == 200
    await session.refresh(ws)
    assert ws.status == "revoked"
    r = await admin_client.delete(f"/api/workstations/{ws.id}?purge=true")
    assert r.status_code == 200
    assert (await session.get(Workstation, ws.id)) is None


@pytest.mark.asyncio
async def test_mine_and_connect_respect_access(admin_client, client, session):
    ws, user = await _seed(session)
    # login as carol
    await client.get("/api/auth/csrf")
    login = await client.post("/api/auth/login",
                              json={"username": "carol", "password": "x"})
    assert login.status_code == 200
    csrf = client.cookies.get("csrf_token")
    client.headers["X-CSRF-Token"] = csrf or ""

    r = await client.get("/api/workstations/mine")
    assert r.status_code == 200 and r.json() == []
    r = await client.get(f"/api/workstations/{ws.id}/connect")
    assert r.status_code == 403

    session.add(WorkstationAccess(workstation_id=ws.id, user_id=user.id))
    await session.commit()
    r = await client.get("/api/workstations/mine")
    assert [w["id"] for w in r.json()] == [ws.id]
    r = await client.get(f"/api/workstations/{ws.id}/connect")
    assert r.status_code == 200
    assert "/w/desk/" in r.json()["url"]
    assert "password" not in r.json()["url"]


@pytest.mark.asyncio
async def test_auth_check_no_cookie_unauthorized(session):
    ws, _ = await _seed(session)
    # Create a fresh unauthenticated client
    from httpx import ASGITransport, AsyncClient
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as fresh_client:
        r = await fresh_client.get("/api/workstations/auth-check",
                                   headers={"X-Forwarded-Uri": f"/w/{ws.subdomain}/"})
        assert r.status_code == 401


@pytest.mark.asyncio
async def test_auth_check_with_access_allowed(admin_client, client, session):
    ws, user = await _seed(session)
    # Login as carol
    await client.get("/api/auth/csrf")
    login = await client.post("/api/auth/login",
                              json={"username": "carol", "password": "x"})
    assert login.status_code == 200
    csrf = client.cookies.get("csrf_token")
    client.headers["X-CSRF-Token"] = csrf or ""

    # Grant access and check auth-check allows
    session.add(WorkstationAccess(workstation_id=ws.id, user_id=user.id))
    await session.commit()
    r = await client.get("/api/workstations/auth-check",
                         headers={"X-Forwarded-Uri": f"/w/{ws.subdomain}/"})
    assert r.status_code == 200
    assert r.json()["ok"] is True


@pytest.mark.asyncio
async def test_auth_check_without_access_forbidden(admin_client, client, session):
    ws, user = await _seed(session)
    # Login as carol (no access granted)
    await client.get("/api/auth/csrf")
    login = await client.post("/api/auth/login",
                              json={"username": "carol", "password": "x"})
    assert login.status_code == 200
    csrf = client.cookies.get("csrf_token")
    client.headers["X-CSRF-Token"] = csrf or ""

    r = await client.get("/api/workstations/auth-check",
                         headers={"X-Forwarded-Uri": f"/w/{ws.subdomain}/"})
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_auth_check_admin_always_allowed(admin_client, session):
    ws, _ = await _seed(session)
    r = await admin_client.get("/api/workstations/auth-check",
                               headers={"X-Forwarded-Uri": f"/w/{ws.subdomain}/"})
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_auth_check_bad_uri_forbidden(admin_client, session):
    ws, _ = await _seed(session)
    r = await admin_client.get("/api/workstations/auth-check",
                               headers={"X-Forwarded-Uri": "/bad/path/"})
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_auth_check_unknown_workstation_forbidden(admin_client, session):
    ws, _ = await _seed(session)
    r = await admin_client.get("/api/workstations/auth-check",
                               headers={"X-Forwarded-Uri": "/w/unknown/"})
    assert r.status_code == 403
