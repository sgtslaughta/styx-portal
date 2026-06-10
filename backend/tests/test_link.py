import pytest
from unittest.mock import AsyncMock, patch
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.models import OAuthProvider, FederatedIdentity
from app.schemas import OAuthIdentity
from app.security.crypto import encrypt_secret
from sqlmodel import select


async def _seed(session):
    session.add(OAuthProvider(name="github", display_label="GitHub", kind="oauth2",
                              client_id="cid", client_secret_enc=encrypt_secret("s")))
    await session.commit()


@pytest.mark.asyncio
async def test_link_then_unlink_allowed_with_password(admin_client, session):
    await _seed(session)
    with patch("app.security.oauth.build_authorize",
               AsyncMock(return_value=("https://idp", "S", "V"))):
        await admin_client.get("/api/auth/link/github/start", follow_redirects=False)
    ident = OAuthIdentity(sub="gh-1", email="admin@x.com", email_verified=True, claims={})
    with patch("app.security.oauth.fetch_identity", AsyncMock(return_value=ident)):
        await admin_client.get("/api/auth/link/github/callback?state=S&code=c",
                               follow_redirects=False)
    listed = await admin_client.get("/api/auth/link/providers")
    assert any(p["provider"] == "github" for p in listed.json())
    r = await admin_client.delete("/api/auth/link/github")
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_link_requires_auth(client):
    r = await client.get("/api/auth/link/providers")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_link_callback_rejects_mismatched_user(admin_client, session):
    # admin starts a github link (tx cookie carries admin's uid)
    await _seed(session)
    with patch("app.security.oauth.build_authorize",
               AsyncMock(return_value=("https://idp", "S", "V"))):
        await admin_client.get("/api/auth/link/github/start", follow_redirects=False)
    tx_cookie = admin_client.cookies.get("oauth_tx")
    assert tx_cookie
    # invite + provision a SECOND user (bob) in a fresh client
    inv = (await admin_client.post("/api/users/invites", json={"role": "user"})).json()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as bob:
        # Bootstrap CSRF for bob
        csrf_r = await bob.get("/api/auth/csrf")
        assert csrf_r.status_code == 200
        csrf = bob.cookies.get("csrf_token")
        assert csrf
        bob.headers.update({"X-CSRF-Token": csrf})

        r = await bob.post("/api/auth/accept-invite", json={
            "token": inv["token"], "username": "bob", "password": "bobs long password"})
        assert r.status_code == 201
        # bob carries admin's tx cookie but is authenticated as bob → must be rejected
        bob.cookies.set("oauth_tx", tx_cookie)
        ident = OAuthIdentity(sub="gh-9", email="bob@x.com", email_verified=True, claims={})
        with patch("app.security.oauth.fetch_identity", AsyncMock(return_value=ident)):
            resp = await bob.get("/api/auth/link/github/callback?state=S&code=c",
                                 follow_redirects=False)
        # rejected: redirected to an error, NOT link=ok
        assert "link=ok" not in resp.headers.get("location", "")
    # no federated identity was created for admin from this attempt
    rows = (await session.exec(select(FederatedIdentity).where(
        FederatedIdentity.subject == "gh-9"))).all()
    assert rows == []
