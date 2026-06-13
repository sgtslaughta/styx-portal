import pytest

from app.security import oauth
from app.schemas import OAuthIdentity


def test_normalize_oidc_claims():
    ident = oauth.normalize_oidc({"sub": "abc", "email": "a@b.c", "email_verified": True,
                                  "groups": ["admins"]})
    assert isinstance(ident, OAuthIdentity)
    assert ident.sub == "abc"
    assert ident.email == "a@b.c"
    assert ident.email_verified is True
    assert ident.claims["groups"] == ["admins"]


def test_normalize_oidc_missing_verified_defaults_false():
    ident = oauth.normalize_oidc({"sub": "abc", "email": "a@b.c"})
    assert ident.email_verified is False


def test_select_github_email_prefers_primary_verified():
    emails = [
        {"email": "old@x.com", "primary": False, "verified": True},
        {"email": "me@x.com", "primary": True, "verified": True},
    ]
    assert oauth.select_github_email(emails) == "me@x.com"


def test_select_github_email_none_when_unverified():
    emails = [{"email": "me@x.com", "primary": True, "verified": False}]
    assert oauth.select_github_email(emails) is None


def test_select_github_email_handles_error_object():
    # GitHub returns an error OBJECT (dict) — not a list — when the token lacks
    # the user:email scope. Iterating it used to yield string keys and crash
    # with "'str' object has no attribute 'get'". Must degrade to None instead.
    err = {"message": "Requires authentication",
           "documentation_url": "https://docs.github.com/..."}
    assert oauth.select_github_email(err) is None


def test_scopes_for_github_overrides_oidc_default():
    from app.models import OAuthProvider
    from app.security.crypto import encrypt_secret
    # A github provider seeded with the OIDC-style default scopes. GitHub does
    # not understand "openid email profile" and grants no email access, so we
    # must substitute GitHub's own scopes.
    p = OAuthProvider(name="github", display_label="GH", kind="oauth2",
                      client_id="cid", client_secret_enc=encrypt_secret("s"),
                      scopes="openid email profile")
    assert oauth.scopes_for(p) == "read:user user:email"


def test_scopes_for_non_github_uses_stored():
    from app.models import OAuthProvider
    from app.security.crypto import encrypt_secret
    p = OAuthProvider(name="authentik", display_label="A", kind="oidc",
                      client_id="cid", client_secret_enc=encrypt_secret("s"),
                      issuer_url="https://idp.test", scopes="openid email profile")
    assert oauth.scopes_for(p) == "openid email profile"


def test_pack_unpack_tx_roundtrip():
    tok = oauth.pack_tx(provider="google", state="st", verifier="vf", mode="login", uid=None)
    data = oauth.unpack_tx(tok)
    assert data["provider"] == "google"
    assert data["state"] == "st"
    assert data["verifier"] == "vf"
    assert data["mode"] == "login"


@pytest.mark.asyncio
async def test_build_authorize_uses_redirect_override(monkeypatch):
    from app.models import OAuthProvider
    from app.security import oauth
    from app.security.crypto import encrypt_secret

    async def fake_endpoints(_p):
        return {"authorize": "https://idp.test/authorize",
                "token": "https://idp.test/token", "userinfo": "https://idp.test/userinfo"}
    monkeypatch.setattr(oauth, "_endpoints", fake_endpoints)

    p = OAuthProvider(name="authentik", display_label="A", kind="oidc",
                      client_id="cid", client_secret_enc=encrypt_secret("s"),
                      issuer_url="https://idp.test")
    url, _state, _verifier = await oauth.build_authorize(
        p, mode="login", redirect_uri="https://app.test/custom/callback")
    assert "redirect_uri=https%3A%2F%2Fapp.test%2Fcustom%2Fcallback" in url
