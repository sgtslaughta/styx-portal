import pytest


@pytest.mark.asyncio
async def test_diagnostics_requires_admin(client):
    assert (await client.get("/api/system/diagnostics")).status_code == 401


@pytest.mark.asyncio
async def test_diagnostics_admin_ok(admin_client):
    r = await admin_client.get("/api/system/diagnostics")
    assert r.status_code == 200
    body = r.json()
    assert "checks" in body and "ok" in body


@pytest.mark.asyncio
async def test_diagnostics_history_admin_ok(admin_client):
    r = await admin_client.get("/api/system/diagnostics/history?range=1h")
    assert r.status_code == 200
    assert "timestamps" in r.json()
