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


@pytest.mark.asyncio
async def test_create_roundtrips_icon_and_trust(admin_client):
    payload = {"name": "authentik", "display_label": "Authentik", "kind": "oidc",
               "issuer_url": "https://idp.test", "client_id": "cid",
               "client_secret": "shh", "scopes": "openid email profile",
               "icon_url": "https://idp.test/logo.svg", "trust_email": True}
    r = await admin_client.post("/api/oauth-providers", json=payload)
    assert r.status_code == 201
    body = r.json()
    assert body["icon_url"] == "https://idp.test/logo.svg"
    assert body["trust_email"] is True


@pytest.mark.asyncio
async def test_update_sets_trust_and_icon(admin_client):
    await admin_client.post("/api/oauth-providers", json=_payload())
    pid = (await admin_client.get("/api/oauth-providers")).json()[0]["id"]
    r = await admin_client.patch(f"/api/oauth-providers/{pid}",
                                 json={"trust_email": True, "icon_url": "https://x.test/i.png"})
    assert r.status_code == 200
    assert r.json()["trust_email"] is True
    assert r.json()["icon_url"] == "https://x.test/i.png"


@pytest.mark.asyncio
async def test_rejects_oversize_data_uri_icon(admin_client):
    big = "data:image/png;base64," + ("A" * 300_000)
    payload = {**_payload(), "name": "big", "icon_url": big}
    r = await admin_client.post("/api/oauth-providers", json=payload)
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_config_check_ok(admin_client, monkeypatch):
    from app.security import oauth
    async def fake_checks(_p):
        return True, [{"label": "Discovery document", "ok": True, "detail": "200"},
                      {"label": "client_id set", "ok": True, "detail": ""}]
    monkeypatch.setattr(oauth, "discovery_checks", fake_checks)
    await admin_client.post("/api/oauth-providers", json=_payload())
    pid = (await admin_client.get("/api/oauth-providers")).json()[0]["id"]
    r = await admin_client.post(f"/api/oauth-providers/{pid}/test/config")
    assert r.status_code == 200
    assert r.json()["ok"] is True
    assert any(c["label"] == "Discovery document" for c in r.json()["checks"])


@pytest.mark.asyncio
async def test_test_login_callback_probes_without_session(admin_client, monkeypatch, session):
    from app.security import oauth
    from app.schemas import OAuthIdentity
    from app.models import FederatedIdentity
    from sqlmodel import select

    async def fake_fetch(provider, mode, url, verifier, redirect_uri=None):
        return OAuthIdentity(sub="ak-1", email="u@e.test", email_verified=False,
                             claims={"sub": "ak-1", "email": "u@e.test"})
    monkeypatch.setattr(oauth, "fetch_identity", fake_fetch)

    await admin_client.post("/api/oauth-providers",
                            json={**_payload(), "name": "authentik", "trust_email": True})
    pid = (await admin_client.get("/api/oauth-providers")).json()[0]["id"]

    # forge a valid test tx cookie
    tx = oauth.pack_tx("authentik", "st8", "vfy", "test", pid)
    admin_client.cookies.set(oauth.TX_COOKIE, tx)
    r = await admin_client.get(
        f"/api/oauth-providers/{pid}/test/callback?state=st8&code=abc")
    assert r.status_code == 200
    assert "u@e.test" in r.text          # identity surfaced in the result page
    assert "would_pass" in r.text
    # probe page carries its own CSP allowing its inline script (global policy is script-src 'self')
    assert "'unsafe-inline'" in r.headers["content-security-policy"]

    # verify no FederatedIdentity was created
    federated_identities = (await session.exec(select(FederatedIdentity))).all()
    assert len(federated_identities) == 0, "test-login should not create FederatedIdentity"

    # verify no auth cookie was set
    assert "access_token" not in r.cookies, "test-login should not set auth cookie"
