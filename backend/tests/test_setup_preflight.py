import pytest


@pytest.mark.asyncio
async def test_preflight_available_before_setup(client):
    r = await client.get("/api/auth/setup-preflight")
    assert r.status_code == 200
    body = r.json()
    assert "docker" in body and "deploy_mode" in body and "domain_set" in body and "data_writable" in body


@pytest.mark.asyncio
async def test_preflight_404_after_user_exists(client):
    r = await client.post("/api/auth/setup", json={
        "username": "admin", "password": "correct horse battery staple"})
    assert r.status_code == 201
    r2 = await client.get("/api/auth/setup-preflight")
    assert r2.status_code == 404
