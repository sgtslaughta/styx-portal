import pytest
from unittest.mock import AsyncMock, patch

from app.models import OAuthProvider, Invite
from app.schemas import OAuthIdentity
from app.security.crypto import encrypt_secret


async def _seed_provider(session):
    p = OAuthProvider(name="google", display_label="Google", kind="oidc",
                      issuer_url="https://accounts.google.test",
                      client_id="cid", client_secret_enc=encrypt_secret("sec"))
    session.add(p)
    await session.commit()
    return p


@pytest.mark.asyncio
async def test_public_providers_lists_enabled(client, session):
    await _seed_provider(session)
    r = await client.get("/api/auth/oauth/providers")
    assert r.status_code == 200
    assert r.json()[0]["name"] == "google"


@pytest.mark.asyncio
async def test_start_sets_tx_cookie_and_redirects(client, session):
    await _seed_provider(session)
    with patch("app.security.oauth.build_authorize",
               AsyncMock(return_value=("https://idp/auth?x=1", "st8", "vf8"))):
        r = await client.get("/api/auth/oauth/google/start", follow_redirects=False)
    assert r.status_code == 302
    assert "idp/auth" in r.headers["location"]
    assert "oauth_tx" in r.cookies


@pytest.mark.asyncio
async def test_callback_provisions_via_invite_and_sets_session(client, session):
    await _seed_provider(session)
    session.add(Invite(token_hash="h", email="new@x.com", role="user", created_by="a"))
    await session.commit()
    with patch("app.security.oauth.build_authorize",
               AsyncMock(return_value=("https://idp/auth", "STATE", "VERIFIER"))):
        await client.get("/api/auth/oauth/google/start", follow_redirects=False)
    ident = OAuthIdentity(sub="g-1", email="new@x.com", email_verified=True, claims={})
    with patch("app.security.oauth.fetch_identity", AsyncMock(return_value=ident)):
        r = await client.get("/api/auth/oauth/google/callback?state=STATE&code=abc",
                             follow_redirects=False)
    assert r.status_code == 302
    assert "access_token" in r.cookies
    me = await client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json()["email"] == "new@x.com"


@pytest.mark.asyncio
async def test_callback_state_mismatch(client, session):
    await _seed_provider(session)
    with patch("app.security.oauth.build_authorize",
               AsyncMock(return_value=("https://idp/auth", "STATE", "VERIFIER"))):
        await client.get("/api/auth/oauth/google/start", follow_redirects=False)
    r = await client.get("/api/auth/oauth/google/callback?state=WRONG&code=abc",
                         follow_redirects=False)
    assert r.status_code == 302
    assert "error=state_mismatch" in r.headers["location"]


@pytest.mark.asyncio
async def test_public_list_includes_icon_url(client, session):
    session.add(OAuthProvider(name="authentik", display_label="Authentik", kind="oidc",
                              client_id="cid", client_secret_enc="x",
                              icon_url="https://idp.test/logo.svg", enabled=True))
    await session.commit()
    r = await client.get("/api/auth/oauth/providers")
    assert r.status_code == 200
    row = next(p for p in r.json() if p["name"] == "authentik")
    assert row["icon_url"] == "https://idp.test/logo.svg"
