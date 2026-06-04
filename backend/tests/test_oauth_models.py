import pytest
from app.models import OAuthProvider, FederatedIdentity


def test_provider_defaults():
    p = OAuthProvider(name="google", display_label="Google", kind="oidc",
                      client_id="cid", client_secret_enc="enc")
    assert p.enabled is True
    assert p.scopes == "openid email profile"
    assert p.role_map == {}
    assert p.id


def test_identity_fields():
    fi = FederatedIdentity(user_id="u1", provider="google", subject="sub123", email="a@b.c")
    assert fi.provider == "google"
    assert fi.subject == "sub123"


@pytest.mark.asyncio
async def test_provider_has_icon_and_trust_defaults(session):
    p = OAuthProvider(name="authentik", display_label="Authentik", kind="oidc",
                      client_id="cid", client_secret_enc="x")
    session.add(p)
    await session.commit()
    await session.refresh(p)
    assert p.icon_url is None
    assert p.trust_email is False
