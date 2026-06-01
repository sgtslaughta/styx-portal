import pytest


def _payload():
    return {"name": "google", "display_label": "Google", "kind": "oidc",
            "issuer_url": "https://accounts.google.test", "client_id": "cid",
            "client_secret": "shh", "scopes": "openid email profile"}


@pytest.mark.asyncio
async def test_create_hides_secret(admin_client):
    r = await admin_client.post("/api/oauth-providers", json=_payload())
    assert r.status_code == 201
    body = r.json()
    assert body["has_secret"] is True
    assert "client_secret" not in body
    assert "client_secret_enc" not in body


@pytest.mark.asyncio
async def test_list_and_update(admin_client):
    await admin_client.post("/api/oauth-providers", json=_payload())
    listed = await admin_client.get("/api/oauth-providers")
    pid = listed.json()[0]["id"]
    r = await admin_client.patch(f"/api/oauth-providers/{pid}", json={"enabled": False})
    assert r.status_code == 200
    assert r.json()["enabled"] is False


@pytest.mark.asyncio
async def test_requires_admin(client):
    r = await client.get("/api/oauth-providers")
    assert r.status_code == 401
