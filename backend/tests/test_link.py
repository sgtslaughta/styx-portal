import pytest
from unittest.mock import AsyncMock, patch

from app.models import OAuthProvider
from app.schemas import OAuthIdentity
from app.security.crypto import encrypt_secret


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
