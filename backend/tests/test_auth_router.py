import pytest


@pytest.mark.asyncio
async def test_setup_required_initially_true(client):
    r = await client.get("/api/auth/setup-required")
    assert r.json()["setup_required"] is True


@pytest.mark.asyncio
async def test_setup_creates_admin_and_locks(client):
    r = await client.post("/api/auth/setup", json={
        "username": "admin", "password": "correct horse battery staple"})
    assert r.status_code == 201
    assert r.json()["role"] == "admin"
    r2 = await client.post("/api/auth/setup", json={
        "username": "user2", "password": "another long password"})
    assert r2.status_code == 404


@pytest.mark.asyncio
async def test_me_after_setup(admin_client):
    r = await admin_client.get("/api/auth/me")
    assert r.status_code == 200
    assert r.json()["username"] == "admin"


@pytest.mark.asyncio
async def test_login_bad_credentials(admin_client):
    r = await admin_client.post("/api/auth/login",
                                json={"username": "admin", "password": "wrong"})
    assert r.status_code == 401


@pytest.mark.xfail(reason="route protected in Task 17", strict=False)
@pytest.mark.asyncio
async def test_unauthenticated_instances_401(client):
    r = await client.get("/api/instances")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_logout_revokes_refresh(admin_client):
    r = await admin_client.post("/api/auth/logout")
    assert r.status_code == 200
    r2 = await admin_client.post("/api/auth/refresh")
    assert r2.status_code == 401
