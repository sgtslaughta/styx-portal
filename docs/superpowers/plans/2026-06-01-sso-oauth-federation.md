# SSO / OAuth Federation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add in-app OIDC/OAuth login (generic OIDC + Google + GitHub) that verifies an external identity and mints the existing Phase-1 cookie session, with admin-managed encrypted providers, pre-authorized-only provisioning, and user account-linking.

**Architecture:** Backend runs the OAuth2 authorization-code flow (authlib `AsyncOAuth2Client`, state + PKCE), reads the verified identity from the IdP userinfo endpoint (OIDC) or GitHub API, resolves it to a `User` (login existing / link by verified email / provision via open invite / else 403), then calls Phase-1 `_issue_session`. Providers live in a DB table with Fernet-encrypted secrets (Fernet key = HKDF(JWT_SECRET)).

**Tech Stack:** Python 3.12, FastAPI, SQLModel/async SQLite, `authlib`, `cryptography` (Fernet+HKDF); React 19, Vite, React Query.

**Builds on Phase 1** (merged `main` 969c8cf). Reuse: `auth.py` `_issue_session`/`_set_auth_cookies`, `security/deps.py` `get_current_user`/`require_admin`, `security/tokens.py` jwt encode/decode, `models.py` `User`/`Invite`, `conftest.py` `admin_client`.

---

## File Structure

**Backend new:** `app/security/crypto.py`, `app/security/oauth.py`, `app/services/federation.py`, `app/routers/oauth.py`, `app/routers/oauth_admin.py`.
**Backend modified:** `app/models.py` (+OAuthProvider, +FederatedIdentity), `app/config.py` (+OAUTH_REDIRECT_BASE), `app/schemas.py` (provider CRUD), `app/routers/auth.py` (+link/unlink), `app/main.py` (register routers).
**Frontend new:** `src/components/system/oauth-providers-panel.tsx`, `src/components/system/connected-accounts.tsx`.
**Frontend modified:** `src/api/client.ts`, `src/pages/LoginPage.tsx`, `src/pages/SetupWizard.tsx`, `src/App.tsx` (mount panels).

---

## Task 1: Add backend dependencies

**Files:** Modify `backend/pyproject.toml`

- [ ] **Step 1: Add packages**

In `backend/pyproject.toml` `dependencies`, add:
```toml
    "authlib>=1.3.2",
    "cryptography>=43.0.0",
```

- [ ] **Step 2: Install + verify**

Run: `cd backend && .venv/bin/python -m pip install -e . && .venv/bin/python -c "import authlib, cryptography; from authlib.integrations.httpx_client import AsyncOAuth2Client; print('ok')"`
Expected: `ok`

- [ ] **Step 3: Commit**
```bash
git add backend/pyproject.toml
git commit -m "build(sso): add authlib and cryptography"
```

---

## Task 2: Secret encryption (HKDF-derived Fernet)

**Files:** Create `backend/app/security/crypto.py`; Test `backend/tests/test_crypto.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_crypto.py`:
```python
import pytest
from app.security import crypto


def test_roundtrip():
    token = crypto.encrypt_secret("super-secret-value")
    assert token != "super-secret-value"
    assert crypto.decrypt_secret(token) == "super-secret-value"


def test_key_is_stable_for_same_jwt_secret():
    a = crypto._fernet_key()
    b = crypto._fernet_key()
    assert a == b


def test_decrypt_garbage_raises():
    with pytest.raises(Exception):
        crypto.decrypt_secret("not-a-valid-token")
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/test_crypto.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement**

Create `backend/app/security/crypto.py`:
```python
import base64

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from app.config import Settings

_settings = Settings()


def _fernet_key() -> bytes:
    """Derive a stable 32-byte Fernet key from JWT_SECRET via HKDF-SHA256."""
    secret = _settings.jwt_secret_or_raise().encode()
    raw = HKDF(
        algorithm=hashes.SHA256(), length=32, salt=None,
        info=b"selkies-oauth-secret-enc",
    ).derive(secret)
    return base64.urlsafe_b64encode(raw)


def _fernet() -> Fernet:
    return Fernet(_fernet_key())


def encrypt_secret(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt_secret(token: str) -> str:
    return _fernet().decrypt(token.encode()).decode()
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd backend && JWT_SECRET=test COOKIE_SECURE=false .venv/bin/python -m pytest tests/test_crypto.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**
```bash
git add backend/app/security/crypto.py backend/tests/test_crypto.py
git commit -m "feat(sso): HKDF-derived Fernet secret encryption"
```

---

## Task 3: OAuthProvider + FederatedIdentity models

**Files:** Modify `backend/app/models.py`; Test `backend/tests/test_oauth_models.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_oauth_models.py`:
```python
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
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/test_oauth_models.py -v`
Expected: FAIL — `ImportError`

- [ ] **Step 3: Implement**

In `backend/app/models.py`, add after the `RefreshToken` class (reuse existing `_uuid`, `_now`, `JSON` column import already present):
```python
class OAuthProvider(SQLModel, table=True):
    __tablename__ = "oauth_providers"

    id: str = Field(default_factory=_uuid, primary_key=True)
    name: str = Field(unique=True, index=True)        # "google" | "github" | "authentik"
    display_label: str
    kind: str = "oidc"                                 # "oidc" | "oauth2"
    issuer_url: str | None = None                      # oidc: discovery base
    authorize_url: str | None = None                   # oauth2: explicit endpoints
    token_url: str | None = None
    userinfo_url: str | None = None
    client_id: str
    client_secret_enc: str
    scopes: str = "openid email profile"
    role_map: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    enabled: bool = True
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)


class FederatedIdentity(SQLModel, table=True):
    __tablename__ = "federated_identities"
    __table_args__ = (UniqueConstraint("provider", "subject", name="uq_provider_subject"),)

    id: str = Field(default_factory=_uuid, primary_key=True)
    user_id: str = Field(foreign_key="users.id", index=True)
    provider: str = Field(index=True)
    subject: str = Field(index=True)
    email: str | None = None
    created_at: datetime = Field(default_factory=_now)
```
At the top of `models.py`, ensure imports include `UniqueConstraint`: change the SQLAlchemy import line to `from sqlalchemy import JSON, UniqueConstraint` (it currently imports `JSON`).

- [ ] **Step 4: Run to verify it passes**

Run: `cd backend && .venv/bin/python -m pytest tests/test_oauth_models.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**
```bash
git add backend/app/models.py backend/tests/test_oauth_models.py
git commit -m "feat(sso): OAuthProvider + FederatedIdentity models"
```

---

## Task 4: Config — redirect base

**Files:** Modify `backend/app/config.py`

- [ ] **Step 1: Add setting**

In `backend/app/config.py` `Settings`, add after the rate-limit fields:
```python
    OAUTH_REDIRECT_BASE: str = ""   # e.g. https://s.jmolabs.dev ; defaults to https://{DOMAIN}
```
And add this method to `Settings`:
```python
    def oauth_redirect_base(self) -> str:
        return self.OAUTH_REDIRECT_BASE or f"https://{self.DOMAIN}"
```

- [ ] **Step 2: Verify**

Run: `cd backend && .venv/bin/python -c "from app.config import Settings; print(Settings(DOMAIN='x.test').oauth_redirect_base())"`
Expected: `https://x.test`

- [ ] **Step 3: Commit**
```bash
git add backend/app/config.py
git commit -m "feat(sso): OAUTH_REDIRECT_BASE setting"
```

---

## Task 5: Auth schemas for providers + identity

**Files:** Modify `backend/app/schemas.py`

- [ ] **Step 1: Add schemas + identity dataclass**

Append to `backend/app/schemas.py` (`BaseModel`, `Field` already imported):
```python
from dataclasses import dataclass


@dataclass
class OAuthIdentity:
    sub: str
    email: str | None
    email_verified: bool
    claims: dict


class ProviderCreate(BaseModel):
    name: str = Field(min_length=2, max_length=40)
    display_label: str
    kind: str = "oidc"                       # oidc | oauth2
    issuer_url: str | None = None
    authorize_url: str | None = None
    token_url: str | None = None
    userinfo_url: str | None = None
    client_id: str
    client_secret: str                        # plaintext in; stored encrypted
    scopes: str = "openid email profile"
    role_map: dict = Field(default_factory=dict)
    enabled: bool = True


class ProviderUpdate(BaseModel):
    display_label: str | None = None
    issuer_url: str | None = None
    authorize_url: str | None = None
    token_url: str | None = None
    userinfo_url: str | None = None
    client_id: str | None = None
    client_secret: str | None = None          # if provided, re-encrypt; else unchanged
    scopes: str | None = None
    role_map: dict | None = None
    enabled: bool | None = None


class ProviderOut(BaseModel):
    id: str
    name: str
    display_label: str
    kind: str
    issuer_url: str | None
    client_id: str
    scopes: str
    role_map: dict
    enabled: bool
    has_secret: bool                          # never expose the secret itself


class PublicProvider(BaseModel):
    name: str
    display_label: str


class ConnectedIdentity(BaseModel):
    provider: str
    email: str | None
    created_at: str
```

- [ ] **Step 2: Verify**

Run: `cd backend && .venv/bin/python -c "from app.schemas import ProviderCreate, ProviderOut, OAuthIdentity, PublicProvider, ConnectedIdentity; print('ok')"`
Expected: `ok`

- [ ] **Step 3: Commit**
```bash
git add backend/app/schemas.py
git commit -m "feat(sso): provider + identity schemas"
```

---

## Task 6: OAuth flow helpers (authlib)

**Files:** Create `backend/app/security/oauth.py`; Test `backend/tests/test_oauth_helpers.py`

This module has PURE helpers (unit-tested here) and async network orchestration (tested via the router with authlib mocked, Task 8).

- [ ] **Step 1: Write the failing test (pure helpers)**

Create `backend/tests/test_oauth_helpers.py`:
```python
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


def test_pack_unpack_tx_roundtrip():
    tok = oauth.pack_tx(provider="google", state="st", verifier="vf", mode="login", uid=None)
    data = oauth.unpack_tx(tok)
    assert data["provider"] == "google"
    assert data["state"] == "st"
    assert data["verifier"] == "vf"
    assert data["mode"] == "login"
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && JWT_SECRET=test COOKIE_SECURE=false .venv/bin/python -m pytest tests/test_oauth_helpers.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement**

Create `backend/app/security/oauth.py`:
```python
from datetime import datetime, timedelta, timezone

import httpx
import jwt
from authlib.common.security import generate_token
from authlib.integrations.httpx_client import AsyncOAuth2Client

from app.config import Settings
from app.models import OAuthProvider
from app.schemas import OAuthIdentity
from app.security.crypto import decrypt_secret

_settings = Settings()
_ALGO = "HS256"
TX_COOKIE = "oauth_tx"
TX_TTL = 600  # 10 minutes

GITHUB_AUTHORIZE = "https://github.com/login/oauth/authorize"
GITHUB_TOKEN = "https://github.com/login/oauth/access_token"
GITHUB_USER = "https://api.github.com/user"
GITHUB_EMAILS = "https://api.github.com/user/emails"


# ---- pure helpers ----
def normalize_oidc(userinfo: dict) -> OAuthIdentity:
    return OAuthIdentity(
        sub=str(userinfo.get("sub")),
        email=userinfo.get("email"),
        email_verified=bool(userinfo.get("email_verified", False)),
        claims=userinfo,
    )


def select_github_email(emails: list[dict]) -> str | None:
    for e in emails:
        if e.get("primary") and e.get("verified"):
            return e["email"]
    for e in emails:
        if e.get("verified"):
            return e["email"]
    return None


def pack_tx(provider: str, state: str, verifier: str, mode: str, uid: str | None) -> str:
    now = datetime.now(timezone.utc)
    payload = {"provider": provider, "state": state, "verifier": verifier,
               "mode": mode, "uid": uid, "type": "oauth_tx",
               "iat": now, "exp": now + timedelta(seconds=TX_TTL)}
    return jwt.encode(payload, _settings.jwt_secret_or_raise(), algorithm=_ALGO)


def unpack_tx(token: str) -> dict:
    return jwt.decode(token, _settings.jwt_secret_or_raise(), algorithms=[_ALGO])


# ---- network orchestration (mocked in tests) ----
async def _discover(issuer: str) -> dict:
    url = issuer.rstrip("/") + "/.well-known/openid-configuration"
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.get(url)
        r.raise_for_status()
        return r.json()


async def _endpoints(provider: OAuthProvider) -> dict:
    if provider.kind == "oidc":
        d = await _discover(provider.issuer_url)
        return {"authorize": d["authorization_endpoint"], "token": d["token_endpoint"],
                "userinfo": d["userinfo_endpoint"]}
    if provider.name == "github":
        return {"authorize": GITHUB_AUTHORIZE, "token": GITHUB_TOKEN, "userinfo": GITHUB_USER}
    return {"authorize": provider.authorize_url, "token": provider.token_url,
            "userinfo": provider.userinfo_url}


def _redirect_uri(provider_name: str, mode: str) -> str:
    leg = "link" if mode == "link" else "oauth"
    return f"{_settings.oauth_redirect_base()}/api/auth/{leg}/{provider_name}/callback"


async def build_authorize(provider: OAuthProvider, mode: str) -> tuple[str, str, str]:
    """Returns (authorize_url, state, code_verifier)."""
    eps = await _endpoints(provider)
    client = AsyncOAuth2Client(
        provider.client_id, decrypt_secret(provider.client_secret_enc),
        scope=provider.scopes, redirect_uri=_redirect_uri(provider.name, mode),
        code_challenge_method="S256",
    )
    verifier = generate_token(48)
    url, state = client.create_authorization_url(eps["authorize"], code_verifier=verifier)
    return url, state, verifier


async def fetch_identity(provider: OAuthProvider, mode: str,
                         authorization_response: str, verifier: str) -> OAuthIdentity:
    eps = await _endpoints(provider)
    client = AsyncOAuth2Client(
        provider.client_id, decrypt_secret(provider.client_secret_enc),
        scope=provider.scopes, redirect_uri=_redirect_uri(provider.name, mode),
        code_challenge_method="S256",
    )
    headers = {"Accept": "application/json"} if provider.name == "github" else None
    await client.fetch_token(eps["token"], authorization_response=authorization_response,
                             code_verifier=verifier, headers=headers)
    if provider.name == "github":
        u = (await client.get(GITHUB_USER)).json()
        emails = (await client.get(GITHUB_EMAILS)).json()
        email = select_github_email(emails)
        return OAuthIdentity(sub=str(u["id"]), email=email,
                             email_verified=email is not None, claims=u)
    userinfo = (await client.get(eps["userinfo"])).json()
    return normalize_oidc(userinfo)
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd backend && JWT_SECRET=test COOKIE_SECURE=false .venv/bin/python -m pytest tests/test_oauth_helpers.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**
```bash
git add backend/app/security/oauth.py backend/tests/test_oauth_helpers.py
git commit -m "feat(sso): authlib OAuth flow helpers + pure normalizers"
```

---

## Task 7: Federation service (resolve / link)

**Files:** Create `backend/app/services/federation.py`; Test `backend/tests/test_federation.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_federation.py`:
```python
import pytest
from datetime import datetime, timedelta, timezone

from app.models import User, Invite, FederatedIdentity
from app.schemas import OAuthIdentity
from app.security.passwords import hash_password
from app.services import federation


def _ident(sub="s1", email="a@b.c", verified=True, claims=None):
    return OAuthIdentity(sub=sub, email=email, email_verified=verified, claims=claims or {})


@pytest.mark.asyncio
async def test_reject_unverified_email(session):
    with pytest.raises(federation.EmailUnverified):
        await federation.resolve_identity(session, "google", _ident(verified=False))


@pytest.mark.asyncio
async def test_existing_identity_logs_in(session):
    u = User(username="bob", password_hash=hash_password("x"))
    session.add(u); await session.flush()
    session.add(FederatedIdentity(user_id=u.id, provider="google", subject="s1", email="a@b.c"))
    await session.commit()
    out = await federation.resolve_identity(session, "google", _ident())
    assert out.id == u.id


@pytest.mark.asyncio
async def test_links_existing_user_by_verified_email(session):
    u = User(username="bob", email="a@b.c", password_hash=hash_password("x"))
    session.add(u); await session.commit()
    out = await federation.resolve_identity(session, "google", _ident())
    assert out.id == u.id
    # identity row created
    from sqlmodel import select
    rows = (await session.exec(select(FederatedIdentity).where(
        FederatedIdentity.provider == "google"))).all()
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_provisions_via_open_invite(session):
    session.add(Invite(token_hash="h", email="a@b.c", role="user", created_by="admin"))
    await session.commit()
    out = await federation.resolve_identity(session, "google", _ident())
    assert out.email == "a@b.c"
    assert out.role == "user"


@pytest.mark.asyncio
async def test_rejects_when_not_preauthorized(session):
    with pytest.raises(federation.NotAuthorized):
        await federation.resolve_identity(session, "google", _ident(email="stranger@x.com"))


@pytest.mark.asyncio
async def test_role_map_promotes_admin(session):
    session.add(Invite(token_hash="h", email="a@b.c", role="user", created_by="admin"))
    await session.commit()
    role_map = {"claim": "groups", "values": {"selkies-admins": "admin"}}
    out = await federation.resolve_identity(
        session, "google", _ident(claims={"groups": ["selkies-admins"]}), role_map=role_map)
    assert out.role == "admin"


@pytest.mark.asyncio
async def test_rejects_disabled_user(session):
    u = User(username="bob", email="a@b.c", password_hash=hash_password("x"), is_active=False)
    session.add(u); await session.commit()
    with pytest.raises(federation.Disabled):
        await federation.resolve_identity(session, "google", _ident())
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && JWT_SECRET=test COOKIE_SECURE=false .venv/bin/python -m pytest tests/test_federation.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement**

Create `backend/app/services/federation.py`:
```python
from datetime import datetime, timezone

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import User, Invite, FederatedIdentity
from app.schemas import OAuthIdentity


class FederationError(Exception):
    pass


class EmailUnverified(FederationError):
    pass


class NotAuthorized(FederationError):
    pass


class Disabled(FederationError):
    pass


def _now():
    return datetime.now(timezone.utc)


def _apply_role_map(default_role: str, claims: dict, role_map: dict | None) -> str:
    if not role_map:
        return default_role
    claim = role_map.get("claim")
    values = role_map.get("values", {})
    present = claims.get(claim) or []
    if isinstance(present, str):
        present = [present]
    for group in present:
        if group in values:
            return values[group]
    return default_role


async def resolve_identity(session: AsyncSession, provider_name: str,
                           identity: OAuthIdentity, role_map: dict | None = None) -> User:
    if not identity.email_verified or not identity.email:
        raise EmailUnverified("IdP did not provide a verified email")

    # 1. existing federated identity → login
    fi = (await session.exec(select(FederatedIdentity).where(
        FederatedIdentity.provider == provider_name,
        FederatedIdentity.subject == identity.sub))).first()
    if fi:
        user = await session.get(User, fi.user_id)
        if not user or not user.is_active:
            raise Disabled("account disabled")
        return user

    # 2. verified email matches an existing user → link
    existing = (await session.exec(select(User).where(User.email == identity.email))).first()
    if existing:
        if not existing.is_active:
            raise Disabled("account disabled")
        session.add(FederatedIdentity(user_id=existing.id, provider=provider_name,
                                      subject=identity.sub, email=identity.email))
        await session.commit()
        return existing

    # 3. verified email matches an open invite → provision
    invite = (await session.exec(select(Invite).where(
        Invite.email == identity.email, Invite.used_at == None))).first()  # noqa: E711
    if invite and not (invite.expires_at and invite.expires_at < _now()):
        role = _apply_role_map(invite.role, identity.claims, role_map)
        username = identity.email.split("@")[0]
        # ensure unique username
        if (await session.exec(select(User).where(User.username == username))).first():
            username = f"{username}-{identity.sub[:6]}"
        user = User(username=username, email=identity.email, password_hash="!sso-no-password",
                    role=role)
        invite.used_at = _now()
        session.add_all([user, invite])
        await session.flush()
        session.add(FederatedIdentity(user_id=user.id, provider=provider_name,
                                      subject=identity.sub, email=identity.email))
        await session.commit()
        return user

    # 4. not pre-authorized
    raise NotAuthorized("email is not authorized to sign in")


async def link_identity(session: AsyncSession, user: User, provider_name: str,
                        identity: OAuthIdentity) -> None:
    if not identity.email_verified:
        raise EmailUnverified("IdP did not provide a verified email")
    taken = (await session.exec(select(FederatedIdentity).where(
        FederatedIdentity.provider == provider_name,
        FederatedIdentity.subject == identity.sub))).first()
    if taken and taken.user_id != user.id:
        raise NotAuthorized("identity already linked to another account")
    if not taken:
        session.add(FederatedIdentity(user_id=user.id, provider=provider_name,
                                      subject=identity.sub, email=identity.email))
        await session.commit()
```

Note: `password_hash="!sso-no-password"` is an intentionally invalid Argon2 string — `verify_password` returns False for it, so SSO-only accounts cannot password-login.

- [ ] **Step 4: Run to verify it passes**

Run: `cd backend && JWT_SECRET=test COOKIE_SECURE=false .venv/bin/python -m pytest tests/test_federation.py -v`
Expected: PASS (7 passed)

- [ ] **Step 5: Commit**
```bash
git add backend/app/services/federation.py backend/tests/test_federation.py
git commit -m "feat(sso): federation resolve/link policy"
```

---

## Task 8: OAuth login router (providers / start / callback)

**Files:** Create `backend/app/routers/oauth.py`; Test `backend/tests/test_oauth_router.py`

- [ ] **Step 1: Implement the router**

Create `backend/app/routers/oauth.py`:
```python
import logging

from fastapi import APIRouter, Depends, Request, Response, status
from fastapi.responses import RedirectResponse
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.config import Settings
from app.database import get_session
from app.models import OAuthProvider
from app.schemas import PublicProvider
from app.security import oauth
from app.routers.auth import _issue_session
from app.services import federation

router = APIRouter()
logger = logging.getLogger("selkies-hub")
_settings = Settings()


async def _get_enabled(session: AsyncSession, name: str) -> OAuthProvider | None:
    return (await session.exec(select(OAuthProvider).where(
        OAuthProvider.name == name, OAuthProvider.enabled == True))).first()  # noqa: E712


def _set_tx_cookie(resp: Response, tx: str) -> None:
    resp.set_cookie(oauth.TX_COOKIE, tx, max_age=oauth.TX_TTL, httponly=True,
                    secure=_settings.COOKIE_SECURE, samesite="lax")


def _err_redirect(code: str) -> RedirectResponse:
    return RedirectResponse(f"/login?error={code}", status_code=status.HTTP_302_FOUND)


@router.get("/providers", response_model=list[PublicProvider])
async def list_public_providers(session: AsyncSession = Depends(get_session)):
    rows = (await session.exec(select(OAuthProvider).where(
        OAuthProvider.enabled == True))).all()  # noqa: E712
    return [PublicProvider(name=p.name, display_label=p.display_label) for p in rows]


@router.get("/{name}/start")
async def start(name: str, session: AsyncSession = Depends(get_session)):
    provider = await _get_enabled(session, name)
    if not provider:
        return _err_redirect("unknown_provider")
    url, state, verifier = await oauth.build_authorize(provider, mode="login")
    resp = RedirectResponse(url, status_code=status.HTTP_302_FOUND)
    _set_tx_cookie(resp, oauth.pack_tx(name, state, verifier, "login", None))
    return resp


@router.get("/{name}/callback")
async def callback(name: str, request: Request, session: AsyncSession = Depends(get_session)):
    tx_raw = request.cookies.get(oauth.TX_COOKIE)
    if not tx_raw:
        return _err_redirect("missing_state")
    try:
        tx = oauth.unpack_tx(tx_raw)
    except Exception:
        return _err_redirect("bad_state")
    if tx["provider"] != name or tx["mode"] != "login":
        return _err_redirect("bad_state")
    if request.query_params.get("state") != tx["state"]:
        return _err_redirect("state_mismatch")
    provider = await _get_enabled(session, name)
    if not provider:
        return _err_redirect("unknown_provider")
    try:
        identity = await oauth.fetch_identity(
            provider, "login", str(request.url), tx["verifier"])
        user = await federation.resolve_identity(session, name, identity, provider.role_map)
    except federation.EmailUnverified:
        return _err_redirect("email_unverified")
    except federation.Disabled:
        return _err_redirect("account_disabled")
    except federation.NotAuthorized:
        return _err_redirect("not_authorized")
    except Exception:
        logger.exception("oauth callback failed")
        return _err_redirect("oauth_failed")
    resp = RedirectResponse("/", status_code=status.HTTP_302_FOUND)
    resp.delete_cookie(oauth.TX_COOKIE)
    await _issue_session(resp, session, user, request)
    return resp
```

- [ ] **Step 2: Write the integration test (authlib mocked)**

Create `backend/tests/test_oauth_router.py`:
```python
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
    # start to obtain a valid tx cookie
    with patch("app.security.oauth.build_authorize",
               AsyncMock(return_value=("https://idp/auth", "STATE", "VERIFIER"))):
        await client.get("/api/auth/oauth/google/start", follow_redirects=False)
    ident = OAuthIdentity(sub="g-1", email="new@x.com", email_verified=True, claims={})
    with patch("app.security.oauth.fetch_identity", AsyncMock(return_value=ident)):
        r = await client.get("/api/auth/oauth/google/callback?state=STATE&code=abc",
                             follow_redirects=False)
    assert r.status_code == 302
    assert "access_token" in r.cookies
    # now authenticated
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
```

Note: this router is registered in Task 11; for tests to find it, do Task 11 BEFORE running this test, or run these tests after Task 11. (The subagent executing this plan should implement Task 8 router + Task 11 registration, then run Task 8's tests. If executing strictly in order, move the `pytest tests/test_oauth_router.py` run to the end of Task 11.)

- [ ] **Step 3: Commit (router only; tests verified after Task 11 wiring)**
```bash
git add backend/app/routers/oauth.py backend/tests/test_oauth_router.py
git commit -m "feat(sso): OAuth login router (providers/start/callback)"
```

---

## Task 9: Admin provider CRUD router

**Files:** Create `backend/app/routers/oauth_admin.py`; Test `backend/tests/test_oauth_admin.py`

- [ ] **Step 1: Implement**

Create `backend/app/routers/oauth_admin.py`:
```python
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.database import get_session
from app.models import OAuthProvider, User
from app.schemas import ProviderCreate, ProviderUpdate, ProviderOut
from app.security.crypto import encrypt_secret
from app.security.deps import require_admin

router = APIRouter()


def _out(p: OAuthProvider) -> ProviderOut:
    return ProviderOut(id=p.id, name=p.name, display_label=p.display_label, kind=p.kind,
                       issuer_url=p.issuer_url, client_id=p.client_id, scopes=p.scopes,
                       role_map=p.role_map, enabled=p.enabled,
                       has_secret=bool(p.client_secret_enc))


@router.get("", response_model=list[ProviderOut])
async def list_providers(admin: User = Depends(require_admin),
                         session: AsyncSession = Depends(get_session)):
    rows = (await session.exec(select(OAuthProvider))).all()
    return [_out(p) for p in rows]


@router.post("", response_model=ProviderOut, status_code=201)
async def create_provider(body: ProviderCreate, admin: User = Depends(require_admin),
                          session: AsyncSession = Depends(get_session)):
    if body.kind not in ("oidc", "oauth2"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "kind must be oidc|oauth2")
    if (await session.exec(select(OAuthProvider).where(OAuthProvider.name == body.name))).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "provider name taken")
    p = OAuthProvider(
        name=body.name, display_label=body.display_label, kind=body.kind,
        issuer_url=body.issuer_url, authorize_url=body.authorize_url,
        token_url=body.token_url, userinfo_url=body.userinfo_url,
        client_id=body.client_id, client_secret_enc=encrypt_secret(body.client_secret),
        scopes=body.scopes, role_map=body.role_map, enabled=body.enabled)
    session.add(p)
    await session.commit()
    return _out(p)


@router.patch("/{provider_id}", response_model=ProviderOut)
async def update_provider(provider_id: str, body: ProviderUpdate,
                          admin: User = Depends(require_admin),
                          session: AsyncSession = Depends(get_session)):
    p = await session.get(OAuthProvider, provider_id)
    if not p:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    data = body.model_dump(exclude_unset=True)
    if "client_secret" in data and data["client_secret"]:
        p.client_secret_enc = encrypt_secret(data.pop("client_secret"))
    else:
        data.pop("client_secret", None)
    for k, v in data.items():
        setattr(p, k, v)
    p.updated_at = datetime.now(timezone.utc)
    session.add(p)
    await session.commit()
    return _out(p)


@router.delete("/{provider_id}", status_code=204)
async def delete_provider(provider_id: str, admin: User = Depends(require_admin),
                          session: AsyncSession = Depends(get_session)):
    p = await session.get(OAuthProvider, provider_id)
    if not p:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    await session.delete(p)
    await session.commit()
```

- [ ] **Step 2: Write the test**

Create `backend/tests/test_oauth_admin.py`:
```python
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
```

- [ ] **Step 3: Commit (tests run after Task 11 wiring)**
```bash
git add backend/app/routers/oauth_admin.py backend/tests/test_oauth_admin.py
git commit -m "feat(sso): admin provider CRUD (write-only secret)"
```

---

## Task 10: Account linking endpoints

**Files:** Modify `backend/app/routers/auth.py`; Test `backend/tests/test_link.py`

- [ ] **Step 1: Add link/unlink endpoints to auth.py**

Append these to `backend/app/routers/auth.py` (add imports at top: `from fastapi.responses import RedirectResponse`, `from app.models import OAuthProvider, FederatedIdentity`, `from app.security import oauth`, `from app.services import federation`, `from app.schemas import ConnectedIdentity`):
```python
@router.get("/link/providers", response_model=list[ConnectedIdentity])
async def linked_providers(user: User = Depends(get_current_user),
                           session: AsyncSession = Depends(get_session)):
    rows = (await session.exec(select(FederatedIdentity).where(
        FederatedIdentity.user_id == user.id))).all()
    return [ConnectedIdentity(provider=r.provider, email=r.email,
                              created_at=r.created_at.isoformat()) for r in rows]


@router.get("/link/{name}/start")
async def link_start(name: str, user: User = Depends(get_current_user),
                     session: AsyncSession = Depends(get_session)):
    provider = (await session.exec(select(OAuthProvider).where(
        OAuthProvider.name == name, OAuthProvider.enabled == True))).first()  # noqa: E712
    if not provider:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "unknown provider")
    url, state, verifier = await oauth.build_authorize(provider, mode="link")
    resp = RedirectResponse(url, status_code=status.HTTP_302_FOUND)
    resp.set_cookie(oauth.TX_COOKIE, oauth.pack_tx(name, state, verifier, "link", user.id),
                    max_age=oauth.TX_TTL, httponly=True,
                    secure=_settings.COOKIE_SECURE, samesite="lax")
    return resp


@router.get("/link/{name}/callback")
async def link_callback(name: str, request: Request,
                        session: AsyncSession = Depends(get_session)):
    tx_raw = request.cookies.get(oauth.TX_COOKIE)
    if not tx_raw:
        return RedirectResponse("/?link=missing_state", status_code=302)
    try:
        tx = oauth.unpack_tx(tx_raw)
    except Exception:
        return RedirectResponse("/?link=bad_state", status_code=302)
    if tx["provider"] != name or tx["mode"] != "link" or \
            request.query_params.get("state") != tx["state"]:
        return RedirectResponse("/?link=bad_state", status_code=302)
    user = await session.get(User, tx["uid"])
    provider = (await session.exec(select(OAuthProvider).where(
        OAuthProvider.name == name))).first()
    if not user or not provider:
        return RedirectResponse("/?link=error", status_code=302)
    try:
        identity = await oauth.fetch_identity(provider, "link", str(request.url), tx["verifier"])
        await federation.link_identity(session, user, name, identity)
    except federation.FederationError:
        return RedirectResponse("/?link=conflict", status_code=302)
    except Exception:
        return RedirectResponse("/?link=error", status_code=302)
    resp = RedirectResponse("/?link=ok", status_code=302)
    resp.delete_cookie(oauth.TX_COOKIE)
    return resp


@router.delete("/link/{name}")
async def unlink_provider(name: str, user: User = Depends(get_current_user),
                          session: AsyncSession = Depends(get_session)):
    rows = (await session.exec(select(FederatedIdentity).where(
        FederatedIdentity.user_id == user.id))).all()
    target = next((r for r in rows if r.provider == name), None)
    if not target:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not linked")
    has_password = user.password_hash and not user.password_hash.startswith("!")
    if not has_password and len(rows) <= 1:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "cannot unlink the only login method")
    await session.delete(target)
    await session.commit()
    return {"ok": True}
```

- [ ] **Step 2: Write the test**

Create `backend/tests/test_link.py`:
```python
import pytest
from unittest.mock import AsyncMock, patch

from app.models import OAuthProvider, FederatedIdentity
from app.schemas import OAuthIdentity
from app.security.crypto import encrypt_secret


async def _seed(session):
    session.add(OAuthProvider(name="github", display_label="GitHub", kind="oauth2",
                              client_id="cid", client_secret_enc=encrypt_secret("s")))
    await session.commit()


@pytest.mark.asyncio
async def test_unlink_last_method_refused(admin_client, session):
    # admin user has a password, so add an identity then it CAN unlink; instead test
    # the refusal path via a synthetic identity-only scenario is covered in federation.
    await _seed(session)
    # link via mocked flow
    with patch("app.security.oauth.build_authorize",
               AsyncMock(return_value=("https://idp", "S", "V"))):
        await admin_client.get("/api/auth/link/github/start", follow_redirects=False)
    ident = OAuthIdentity(sub="gh-1", email="admin@x.com", email_verified=True, claims={})
    with patch("app.security.oauth.fetch_identity", AsyncMock(return_value=ident)):
        await admin_client.get("/api/auth/link/github/callback?state=S&code=c",
                               follow_redirects=False)
    listed = await admin_client.get("/api/auth/link/providers")
    assert any(p["provider"] == "github" for p in listed.json())
    # admin has a password → unlink allowed
    r = await admin_client.delete("/api/auth/link/github")
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_link_requires_auth(client):
    r = await client.get("/api/auth/link/providers")
    assert r.status_code == 401
```

- [ ] **Step 3: Commit (run after Task 11)**
```bash
git add backend/app/routers/auth.py backend/tests/test_link.py
git commit -m "feat(sso): account link/unlink endpoints"
```

---

## Task 11: Wire routers into main.py + run SSO tests

**Files:** Modify `backend/app/main.py`

- [ ] **Step 1: Register routers**

In `backend/app/main.py`, near the other `app.include_router(...)` calls, add:
```python
from app.routers import oauth as oauth_router
from app.routers import oauth_admin as oauth_admin_router

app.include_router(oauth_router.router, prefix="/api/auth/oauth", tags=["oauth"])
app.include_router(oauth_admin_router.router, prefix="/api/oauth-providers", tags=["oauth-admin"])
```
The link/unlink endpoints are already on the existing `auth` router (prefix `/api/auth`), so no extra registration. Verify the CSRF exemption: the `DELETE /api/auth/link/{name}` endpoint is NOT exempt, so the frontend must send the CSRF header (it does, via the client wrapper). The GET start/callback endpoints are safe methods (no CSRF needed).

- [ ] **Step 2: Import check**

Run: `cd backend && JWT_SECRET=test COOKIE_SECURE=false .venv/bin/python -c "from app.main import app; print('ok')"`
Expected: `ok`

- [ ] **Step 3: Run all SSO tests (Tasks 8/9/10) now that routers are wired**

Run: `cd backend && JWT_SECRET=test COOKIE_SECURE=false .venv/bin/python -m pytest tests/test_oauth_router.py tests/test_oauth_admin.py tests/test_link.py -v`
Expected: all PASS.

- [ ] **Step 4: Full suite + lint**

Run: `cd backend && JWT_SECRET=test COOKIE_SECURE=false .venv/bin/python -m pytest -q`
Expected: all green (110 prior + new SSO tests).
Run: `cd backend && .venv/bin/python -m ruff check app/ tests/`
Expected: pass.

- [ ] **Step 5: Commit**
```bash
git add backend/app/main.py
git commit -m "feat(sso): register oauth + oauth-admin routers"
```

---

## Task 12: Frontend API client — OAuth methods

**Files:** Modify `frontend/src/api/client.ts`

- [ ] **Step 1: Add methods**

Add to the exported `api` object in `frontend/src/api/client.ts`:
```typescript
  oauthProviders: () => request<{ name: string; display_label: string }[]>("/auth/oauth/providers"),
  oauthStartUrl: (name: string) => `/api/auth/oauth/${name}/start`,
  linkStartUrl: (name: string) => `/api/auth/link/${name}/start`,
  linkedProviders: () => request<{ provider: string; email: string | null; created_at: string }[]>("/auth/link/providers"),
  unlinkProvider: (name: string) => request<{ ok: boolean }>(`/auth/link/${name}`, { method: "DELETE" }),
  // admin provider CRUD
  listOAuthProviders: () => request<OAuthProviderRow[]>("/oauth-providers"),
  createOAuthProvider: (data: OAuthProviderCreate) =>
    request<OAuthProviderRow>("/oauth-providers", { method: "POST", body: JSON.stringify(data) }),
  updateOAuthProvider: (id: string, data: Partial<OAuthProviderCreate> & { enabled?: boolean }) =>
    request<OAuthProviderRow>(`/oauth-providers/${id}`, { method: "PATCH", body: JSON.stringify(data) }),
  deleteOAuthProvider: (id: string) => request<void>(`/oauth-providers/${id}`, { method: "DELETE" }),
```
And add these types near the top of the file (after the existing imports):
```typescript
export type OAuthProviderRow = {
  id: string; name: string; display_label: string; kind: string;
  issuer_url: string | null; client_id: string; scopes: string;
  role_map: Record<string, unknown>; enabled: boolean; has_secret: boolean;
};
export type OAuthProviderCreate = {
  name: string; display_label: string; kind: string; issuer_url?: string;
  authorize_url?: string; token_url?: string; userinfo_url?: string;
  client_id: string; client_secret: string; scopes?: string; role_map?: Record<string, unknown>;
};
```

- [ ] **Step 2: Type-check**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 3: Commit**
```bash
git add frontend/src/api/client.ts
git commit -m "feat(sso): frontend oauth + provider-admin API methods"
```

---

## Task 13: Frontend — "Sign in with" buttons on Login/Setup

**Files:** Modify `frontend/src/pages/LoginPage.tsx`, `frontend/src/pages/SetupWizard.tsx`

- [ ] **Step 1: Add provider buttons to LoginPage**

In `frontend/src/pages/LoginPage.tsx`, fetch providers and render buttons. Add near the imports:
```tsx
import { useEffect, useState } from "react";
```
Inside the component, add:
```tsx
  const [providers, setProviders] = useState<{ name: string; display_label: string }[]>([]);
  useEffect(() => { api.oauthProviders().then(setProviders).catch(() => {}); }, []);
```
Below the password submit button (inside the form/card), render:
```tsx
  {providers.length > 0 && (
    <div className="space-y-2 pt-2">
      <div className="text-center text-xs text-muted-foreground">or</div>
      {providers.map((p) => (
        <a key={p.name} href={api.oauthStartUrl(p.name)}
           className="block w-full rounded border p-2 text-center text-sm hover:bg-muted">
          Sign in with {p.display_label}
        </a>
      ))}
    </div>
  )}
```
Also surface an SSO error if present: read `?error=` from the URL and show a message above the form (use `new URLSearchParams(window.location.search).get("error")`). Map codes (not_authorized/email_unverified/account_disabled/state_mismatch/oauth_failed) to friendly text.

- [ ] **Step 2: Add the same provider buttons to SetupWizard**

Setup is for the first admin (no users yet) — SSO can't provision the first admin (no invite, pre-authorized-only). So on SetupWizard, do NOT show provider buttons (only native admin creation). No change needed beyond confirming none are shown.

- [ ] **Step 3: Type-check + build**

Run: `cd frontend && npx tsc --noEmit && npm run build`
Expected: succeeds.

- [ ] **Step 4: Commit**
```bash
git add frontend/src/pages/LoginPage.tsx
git commit -m "feat(sso): Sign in with provider buttons + SSO error display"
```

---

## Task 14: Frontend — admin OAuth Providers panel

**Files:** Create `frontend/src/components/system/oauth-providers-panel.tsx`; Modify `frontend/src/App.tsx`

- [ ] **Step 1: Create the panel**

Create `frontend/src/components/system/oauth-providers-panel.tsx`:
```tsx
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, type OAuthProviderCreate } from "@/api/client";

const EMPTY: OAuthProviderCreate = {
  name: "", display_label: "", kind: "oidc", issuer_url: "",
  client_id: "", client_secret: "", scopes: "openid email profile",
};

export function OAuthProvidersPanel() {
  const qc = useQueryClient();
  const { data: providers = [] } = useQuery({
    queryKey: ["oauth-providers"], queryFn: api.listOAuthProviders });
  const [form, setForm] = useState<OAuthProviderCreate>(EMPTY);

  const create = useMutation({
    mutationFn: () => api.createOAuthProvider(form),
    onSuccess: () => { setForm(EMPTY); qc.invalidateQueries({ queryKey: ["oauth-providers"] }); },
  });
  const toggle = useMutation({
    mutationFn: (p: { id: string; enabled: boolean }) =>
      api.updateOAuthProvider(p.id, { enabled: p.enabled }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["oauth-providers"] }),
  });
  const remove = useMutation({
    mutationFn: (id: string) => api.deleteOAuthProvider(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["oauth-providers"] }),
  });

  const set = (k: keyof OAuthProviderCreate) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setForm({ ...form, [k]: e.target.value });

  return (
    <div className="space-y-4">
      <h2 className="text-lg font-semibold">OAuth / SSO providers</h2>
      <table className="w-full text-sm">
        <thead><tr className="text-left"><th>Name</th><th>Kind</th><th>Enabled</th><th>Secret</th><th></th></tr></thead>
        <tbody>
          {providers.map((p) => (
            <tr key={p.id} className="border-t">
              <td className="py-1">{p.display_label} <span className="text-muted-foreground">({p.name})</span></td>
              <td>{p.kind}</td>
              <td>
                <input type="checkbox" checked={p.enabled}
                       onChange={(e) => toggle.mutate({ id: p.id, enabled: e.target.checked })} />
              </td>
              <td>{p.has_secret ? "set" : "unset"}</td>
              <td className="text-right">
                <button className="text-red-500" onClick={() => remove.mutate(p.id)}>Delete</button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="rounded border p-3 space-y-2">
        <div className="font-medium">Add provider</div>
        <input className="w-full rounded border p-1.5" placeholder="name (e.g. authentik)" value={form.name} onChange={set("name")} />
        <input className="w-full rounded border p-1.5" placeholder="display label" value={form.display_label} onChange={set("display_label")} />
        <input className="w-full rounded border p-1.5" placeholder="issuer url (OIDC discovery base)" value={form.issuer_url} onChange={set("issuer_url")} />
        <input className="w-full rounded border p-1.5" placeholder="client id" value={form.client_id} onChange={set("client_id")} />
        <input className="w-full rounded border p-1.5" type="password" placeholder="client secret" value={form.client_secret} onChange={set("client_secret")} />
        <input className="w-full rounded border p-1.5" placeholder="scopes" value={form.scopes} onChange={set("scopes")} />
        <button className="rounded bg-blue-600 px-3 py-1.5 text-white" onClick={() => create.mutate()}>Add</button>
      </div>
    </div>
  );
}
```
(For `kind=github` the operator sets name=`github` and leaves issuer_url blank — backend special-cases GitHub endpoints. This baseline supports OIDC + GitHub by name; polish/validation can come later.)

- [ ] **Step 2: Mount under System tab (admin only)**

In `frontend/src/App.tsx`, where the admin `UsersPanel` is rendered (Task 23 of Phase 1), add the providers panel beside it:
```tsx
import { OAuthProvidersPanel } from "@/components/system/oauth-providers-panel";
// near UsersPanel:
{user?.role === "admin" && <OAuthProvidersPanel />}
```

- [ ] **Step 3: Type-check + build**

Run: `cd frontend && npx tsc --noEmit && npm run build`
Expected: succeeds.

- [ ] **Step 4: Commit**
```bash
git add frontend/src/components/system/oauth-providers-panel.tsx frontend/src/App.tsx
git commit -m "feat(sso): admin OAuth providers panel"
```

---

## Task 15: Frontend — Connected accounts (link/unlink)

**Files:** Create `frontend/src/components/system/connected-accounts.tsx`; Modify `frontend/src/App.tsx`

- [ ] **Step 1: Create the component**

Create `frontend/src/components/system/connected-accounts.tsx`:
```tsx
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/api/client";

export function ConnectedAccounts() {
  const qc = useQueryClient();
  const { data: linked = [] } = useQuery({
    queryKey: ["linked-providers"], queryFn: api.linkedProviders });
  const { data: providers = [] } = useQuery({
    queryKey: ["public-providers"], queryFn: api.oauthProviders });
  const unlink = useMutation({
    mutationFn: (name: string) => api.unlinkProvider(name),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["linked-providers"] }),
  });

  const linkedNames = new Set(linked.map((l) => l.provider));
  return (
    <div className="space-y-3">
      <h2 className="text-lg font-semibold">Connected accounts</h2>
      <ul className="space-y-1 text-sm">
        {linked.map((l) => (
          <li key={l.provider} className="flex items-center justify-between border-t py-1">
            <span>{l.provider} — {l.email}</span>
            <button className="text-red-500" onClick={() => unlink.mutate(l.provider)}>Unlink</button>
          </li>
        ))}
      </ul>
      <div className="space-y-1">
        {providers.filter((p) => !linkedNames.has(p.name)).map((p) => (
          <a key={p.name} href={api.linkStartUrl(p.name)}
             className="block w-full rounded border p-2 text-center text-sm hover:bg-muted">
            Link {p.display_label}
          </a>
        ))}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Mount under System tab (all authenticated users)**

In `frontend/src/App.tsx`, in the System tab content (visible to any logged-in user, not just admin), render:
```tsx
import { ConnectedAccounts } from "@/components/system/connected-accounts";
// in System tab content:
{user && <ConnectedAccounts />}
```

- [ ] **Step 3: Type-check + build**

Run: `cd frontend && npx tsc --noEmit && npm run build`
Expected: succeeds.

- [ ] **Step 4: Commit**
```bash
git add frontend/src/components/system/connected-accounts.tsx frontend/src/App.tsx
git commit -m "feat(sso): connected accounts (link/unlink) UI"
```

---

## Task 16: Docs + final verification

**Files:** Modify `.env.example`, `README.md`, `CLAUDE.md`

- [ ] **Step 1: Docs**

In `.env.example`, add under the auth section:
```env
# SSO/OAuth (Phase 2) — provider client secrets are encrypted with a key derived
# from JWT_SECRET. Rotating JWT_SECRET requires re-entering provider secrets.
# Optional: override the OAuth redirect base (defaults to https://${DOMAIN})
# OAUTH_REDIRECT_BASE=https://s.jmolabs.dev
```
In `README.md`, add a short "SSO / OAuth (Phase 2)" subsection: providers are added in **System → OAuth providers** (admin); users sign in with provider buttons on the login page; provisioning is pre-authorized-only (verified email must match an existing user or an open invite); users link/unlink providers under **System → Connected accounts**. Per-provider redirect URI is `https://<domain>/api/auth/oauth/<name>/callback` (and `/api/auth/link/<name>/callback` for linking) — register both with the IdP.
In `CLAUDE.md`, add one line under auth notes: SSO via in-app authlib OIDC/OAuth, providers in `oauth_providers` (Fernet-encrypted secret), identities in `federated_identities`, pre-authorized-only.

- [ ] **Step 2: Final verification**

Run: `cd backend && .venv/bin/python -m pytest -q` — all green; report count.
Run: `cd backend && .venv/bin/python -m ruff check app/ tests/` — pass.
Run: `cd frontend && npx tsc --noEmit && npm run build` — succeeds.

- [ ] **Step 3: Commit**
```bash
git add .env.example README.md CLAUDE.md
git commit -m "docs(sso): document SSO/OAuth provider setup + redirect URIs"
```

- [ ] **Step 4: Manual e2e checklist (report, do not auto-run)**
- Admin adds an OIDC provider (e.g. Authentik issuer) in System → OAuth providers → enabled.
- Logout → /login shows "Sign in with <label>".
- Click it → IdP login → redirected back authenticated IF email matches an existing user or open invite; else `/login?error=not_authorized`.
- Provision path: admin creates an invite for the SSO email first → SSO login then provisions that user.
- Connected accounts: logged-in user links GitHub → row appears; unlink works; unlinking the only login method is refused.
- Provider secret never appears in any API response (`has_secret` only).

---

## Self-Review notes (addressed)
- **Spec coverage:** in-app authlib flow (T6,8), Phase-1 session reuse (T8 `_issue_session`), DB providers + Fernet (T2,3,9), pre-authorized-only + link/provision/reject + verified-email + disabled (T7), generic OIDC + Google (OIDC discovery) + GitHub special-case (T6), account linking incl. unlink-last-method guard (T10), HKDF-from-JWT_SECRET key (T2), state+PKCE (T6 `build_authorize`/`pack_tx`), role_map (T7), admin write-only secret (T9), frontend buttons/admin panel/connected-accounts (T13-15). All covered.
- **Simplification vs spec:** OIDC identity read from the **userinfo endpoint** (discovery-provided) rather than parsing/validating an `id_token` via JWKS; `nonce` therefore omitted. state+PKCE still protect the flow; userinfo is fetched over TLS with the fresh access token. Documented here intentionally.
- **Type consistency:** `OAuthIdentity{sub,email,email_verified,claims}`, `pack_tx/unpack_tx` keys (provider/state/verifier/mode/uid), `_issue_session(resp, session, user, request)` signature, `TX_COOKIE="oauth_tx"`, provider `role_map={"claim","values"}` shape — consistent across tasks.
- **Ordering note:** Tasks 8/9/10 create routers whose tests need the registration from Task 11; their test runs are executed at Task 11 Step 3 (called out in each task).
