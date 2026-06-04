# SSO Provider UX Polish + Verified-Email Fix — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make SSO provider admin a modal-based add/edit flow with per-provider icon + email-trust, add config/login test tooling, and fix the Authentik "verified email" rejection.

**Architecture:** Two new `OAuthProvider` columns (`icon_url`, `trust_email`) flow through schema → router → frontend. The verified-email gate moves its trust decision into `federation` (provider record available there). Provider testing adds a server-side config check and a no-session OAuth round-trip. Frontend replaces the inline add form with a reusable `<Dialog>` used for both add and edit, plus icon upload and login-page icons.

**Tech Stack:** FastAPI, SQLModel, async SQLite, httpx, authlib (backend); React 19, TanStack Query, Radix Dialog, framer-motion, lucide-react, sonner toasts (frontend).

**Spec:** `docs/superpowers/specs/2026-06-04-sso-provider-ux-design.md`

**Verification commands:**
- Backend tests: `cd backend && .venv/bin/python -m pytest -v`
- Backend lint: `cd backend && .venv/bin/python -m ruff check app/ tests/`
- Frontend typecheck: `cd frontend && npm run lint`
- Frontend build: `cd frontend && npm run build`

> Frontend has **no unit-test runner** (lint = `tsc --noEmit`). Frontend tasks verify via typecheck + build + explicit manual steps. Backend tasks use TDD with pytest.

---

## File Structure

Backend:
- `backend/app/models.py` — add 2 columns to `OAuthProvider`.
- `backend/app/database.py` — add 2 migration rows.
- `backend/app/schemas.py` — provider Create/Update/Out fields; `PublicProvider.icon_url`; new `ProviderTestResult`, `ProviderTestCheck`, `IdentityProbe` schemas.
- `backend/app/services/federation.py` — `trust_email` gate in `resolve_identity` + `link_identity`.
- `backend/app/security/oauth.py` — optional `redirect_uri` override on `build_authorize`/`fetch_identity`; new `discovery_checks` helper.
- `backend/app/routers/oauth_admin.py` — `_out` adds fields; create/update icon validation + pass-through; `test/config`, `test/start`, `test/callback` endpoints.
- `backend/app/routers/oauth.py` — public list adds `icon_url`.
- `backend/app/routers/auth.py` — pass `provider.trust_email` into `link_identity`.

Frontend:
- `frontend/src/api/client.ts` — types + test API methods.
- `frontend/src/components/system/provider-dialog.tsx` — NEW add/edit modal.
- `frontend/src/components/system/oauth-providers-panel.tsx` — slimmed list + Add/Edit buttons.
- `frontend/src/pages/LoginPage.tsx` — provider icons.

---

## Task 1: Add `icon_url` + `trust_email` columns

**Files:**
- Modify: `backend/app/models.py:55-72`
- Modify: `backend/app/database.py:31-36`
- Test: `backend/tests/test_oauth_models.py`

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_oauth_models.py`:

```python
@pytest.mark.asyncio
async def test_provider_has_icon_and_trust_defaults(session):
    from app.models import OAuthProvider
    p = OAuthProvider(name="authentik", display_label="Authentik", kind="oidc",
                      client_id="cid", client_secret_enc="x")
    session.add(p)
    await session.commit()
    await session.refresh(p)
    assert p.icon_url is None
    assert p.trust_email is False
```

(If `test_oauth_models.py` has no `import pytest` / `session` fixture usage, mirror the imports already at the top of that file.)

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/test_oauth_models.py::test_provider_has_icon_and_trust_defaults -v`
Expected: FAIL — `AttributeError` / unexpected keyword (no `icon_url`/`trust_email`).

- [ ] **Step 3: Add the columns**

In `backend/app/models.py`, inside `class OAuthProvider`, after line 68 (`scopes: str = ...`) add:

```python
    icon_url: str | None = None                        # remote URL or base64 data URI
    trust_email: bool = False                          # treat missing email_verified as verified
```

In `backend/app/database.py`, extend the `migrations` list (after line 35 `("service_templates", "dind", "BOOLEAN"),`):

```python
        ("oauth_providers", "icon_url", "TEXT"),
        ("oauth_providers", "trust_email", "BOOLEAN"),
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/bin/python -m pytest tests/test_oauth_models.py::test_provider_has_icon_and_trust_defaults -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/models.py backend/app/database.py backend/tests/test_oauth_models.py
git commit -m "feat(sso): add icon_url + trust_email columns to oauth_providers"
```

---

## Task 2: Schema fields for icon + trust

**Files:**
- Modify: `backend/app/schemas.py:121-165`
- Test: `backend/tests/test_oauth_admin.py`

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_oauth_admin.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/test_oauth_admin.py::test_create_roundtrips_icon_and_trust -v`
Expected: FAIL — response has no `icon_url`/`trust_email` (KeyError on assert).

- [ ] **Step 3: Add schema fields**

In `backend/app/schemas.py`:

`ProviderCreate` — after line 132 (`role_map: dict = ...`) add:
```python
    icon_url: str | None = None
    trust_email: bool = False
```

`ProviderUpdate` — after line 145 (`role_map: dict | None = None`) add:
```python
    icon_url: str | None = None
    trust_email: bool | None = None
```

`ProviderOut` — after line 157 (`role_map: dict`) add:
```python
    icon_url: str | None
    trust_email: bool
```

`PublicProvider` — change body to:
```python
class PublicProvider(BaseModel):
    name: str
    display_label: str
    icon_url: str | None = None
```

(Router `_out` is updated in Task 4 — this task only changes schemas; the test passes once Task 4's `_out` change lands. To keep this task green on its own, also do Task 4 Step 3's `_out` edit here OR run this test after Task 4. Recommended: implement Task 4 `_out` edit now too, since they're inseparable — see note.)

> **Note:** `ProviderOut` is constructed by `_out()` in `oauth_admin.py`. Adding fields to the schema without updating `_out` raises a validation error. So in Step 3 ALSO apply the `_out` change from Task 4 Step 3. Task 4 then only adds the create/update pass-through + validation.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/bin/python -m pytest tests/test_oauth_admin.py::test_create_roundtrips_icon_and_trust -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/schemas.py backend/app/routers/oauth_admin.py backend/tests/test_oauth_admin.py
git commit -m "feat(sso): icon_url + trust_email in provider schemas"
```

---

## Task 3: Verified-email trust gate in federation

**Files:**
- Modify: `backend/app/services/federation.py:44-47, 91-94`
- Modify: `backend/app/routers/oauth.py:72`
- Modify: `backend/app/routers/auth.py:216`
- Test: `backend/tests/test_federation.py`

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_federation.py`:

```python
@pytest.mark.asyncio
async def test_trust_email_allows_unverified(session):
    from app.models import Invite
    session.add(Invite(token_hash="h", email="a@b.c", role="user", created_by="admin"))
    await session.commit()
    out = await federation.resolve_identity(
        session, "authentik", _ident(verified=False), trust_email=True)
    assert out.email == "a@b.c"

@pytest.mark.asyncio
async def test_no_email_always_rejected_even_with_trust(session):
    with pytest.raises(federation.EmailUnverified):
        await federation.resolve_identity(
            session, "authentik", _ident(verified=False, email=None), trust_email=True)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && .venv/bin/python -m pytest tests/test_federation.py::test_trust_email_allows_unverified tests/test_federation.py::test_no_email_always_rejected_even_with_trust -v`
Expected: FAIL — `resolve_identity()` got unexpected keyword `trust_email`.

- [ ] **Step 3: Add the trust_email parameter + gate**

In `backend/app/services/federation.py`, replace lines 44-47:

```python
async def resolve_identity(session: AsyncSession, provider_name: str,
                           identity: OAuthIdentity, role_map: dict | None = None,
                           trust_email: bool = False) -> User:
    if not identity.email:
        raise EmailUnverified("IdP did not provide an email")
    if not identity.email_verified and not trust_email:
        raise EmailUnverified("IdP did not provide a verified email")
```

Replace lines 91-94 (`link_identity` signature + first check):

```python
async def link_identity(session: AsyncSession, user: User, provider_name: str,
                        identity: OAuthIdentity, trust_email: bool = False) -> None:
    if not identity.email_verified and not trust_email:
        raise EmailUnverified("IdP did not provide a verified email")
```

In `backend/app/routers/oauth.py` line 72, pass trust_email:
```python
        user = await federation.resolve_identity(
            session, name, identity, provider.role_map, provider.trust_email)
```

In `backend/app/routers/auth.py` line 216, pass trust_email:
```python
        await federation.link_identity(session, user, name, identity, provider.trust_email)
```

- [ ] **Step 4: Run the full federation + router suites**

Run: `cd backend && .venv/bin/python -m pytest tests/test_federation.py tests/test_oauth_router.py -v`
Expected: PASS (including existing `test_reject_unverified_email`, which calls with default `trust_email=False`).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/federation.py backend/app/routers/oauth.py backend/app/routers/auth.py backend/tests/test_federation.py
git commit -m "fix(sso): per-provider trust_email skips verified-email check"
```

---

## Task 4: Router pass-through + icon validation

**Files:**
- Modify: `backend/app/routers/oauth_admin.py:16-45`
- Test: `backend/tests/test_oauth_admin.py`

> `_out` was already updated in Task 2. This task adds create/update field pass-through + data-URI size validation.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_oauth_admin.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && .venv/bin/python -m pytest tests/test_oauth_admin.py::test_update_sets_trust_and_icon tests/test_oauth_admin.py::test_rejects_oversize_data_uri_icon -v`
Expected: FAIL — trust/icon not persisted; oversize icon returns 201 not 422.

- [ ] **Step 3: Update router**

In `backend/app/routers/oauth_admin.py`:

Replace `_out` (lines 16-20) — adds the two fields (do here if not already done in Task 2):
```python
def _out(p: OAuthProvider) -> ProviderOut:
    return ProviderOut(id=p.id, name=p.name, display_label=p.display_label, kind=p.kind,
                       issuer_url=p.issuer_url, client_id=p.client_id, scopes=p.scopes,
                       role_map=p.role_map, enabled=p.enabled,
                       has_secret=bool(p.client_secret_enc),
                       icon_url=p.icon_url, trust_email=p.trust_email)
```

Add an icon validator above `list_providers` (after line 20):
```python
MAX_ICON_BYTES = 256 * 1024


def _validate_icon(icon_url: str | None) -> None:
    if icon_url and icon_url.startswith("data:"):
        if not icon_url.startswith("data:image/"):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "icon must be an image data URI")
        if len(icon_url) > MAX_ICON_BYTES:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "icon data URI too large (max 256KB)")
```

In `create_provider`, after the kind check (line 34) add `_validate_icon(body.icon_url)`, and extend the `OAuthProvider(...)` constructor (lines 37-42) with:
```python
        icon_url=body.icon_url, trust_email=body.trust_email,
```

In `update_provider`, after `data = body.model_dump(exclude_unset=True)` (line 55) add:
```python
    if "icon_url" in data:
        _validate_icon(data["icon_url"])
```
(The existing `for k, v in data.items(): setattr(p, k, v)` loop already persists `icon_url`/`trust_email`.)

- [ ] **Step 4: Run the admin suite**

Run: `cd backend && .venv/bin/python -m pytest tests/test_oauth_admin.py -v`
Expected: PASS (all, including Task 2's roundtrip test).

- [ ] **Step 5: Commit**

```bash
git add backend/app/routers/oauth_admin.py backend/tests/test_oauth_admin.py
git commit -m "feat(sso): persist icon_url/trust_email + validate icon data URIs"
```

---

## Task 5: Public providers list exposes icon_url

**Files:**
- Modify: `backend/app/routers/oauth.py:35-39`
- Test: `backend/tests/test_oauth_router.py`

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_oauth_router.py` (mirror existing imports/fixtures in that file — it already creates providers; if a helper exists reuse it):

```python
@pytest.mark.asyncio
async def test_public_list_includes_icon_url(client, session):
    from app.models import OAuthProvider
    session.add(OAuthProvider(name="authentik", display_label="Authentik", kind="oidc",
                              client_id="cid", client_secret_enc="x",
                              icon_url="https://idp.test/logo.svg", enabled=True))
    await session.commit()
    r = await client.get("/api/auth/oauth/providers")
    assert r.status_code == 200
    row = next(p for p in r.json() if p["name"] == "authentik")
    assert row["icon_url"] == "https://idp.test/logo.svg"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/test_oauth_router.py::test_public_list_includes_icon_url -v`
Expected: FAIL — `icon_url` missing from response row.

- [ ] **Step 3: Update the endpoint**

In `backend/app/routers/oauth.py`, replace line 39:
```python
    return [PublicProvider(name=p.name, display_label=p.display_label,
                           icon_url=p.icon_url) for p in rows]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/bin/python -m pytest tests/test_oauth_router.py::test_public_list_includes_icon_url -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/routers/oauth.py backend/tests/test_oauth_router.py
git commit -m "feat(sso): public provider list returns icon_url"
```

---

## Task 6: redirect_uri override in oauth helpers

**Files:**
- Modify: `backend/app/security/oauth.py:81-112`
- Test: `backend/tests/test_oauth_helpers.py`

> Test endpoints (Task 8) use a callback path different from the live flow. Adding an optional `redirect_uri` override keeps `build_authorize`/`fetch_identity` reusable without duplicating their logic.

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_oauth_helpers.py` (mirror existing imports; it already imports `oauth` and builds providers — reuse any provider factory present):

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/test_oauth_helpers.py::test_build_authorize_uses_redirect_override -v`
Expected: FAIL — `build_authorize()` got unexpected keyword `redirect_uri`.

- [ ] **Step 3: Add the override param**

In `backend/app/security/oauth.py`, replace `build_authorize` (lines 81-91):
```python
async def build_authorize(provider: OAuthProvider, mode: str,
                          redirect_uri: str | None = None) -> tuple[str, str, str]:
    """Returns (authorize_url, state, code_verifier)."""
    eps = await _endpoints(provider)
    client = AsyncOAuth2Client(
        provider.client_id, decrypt_secret(provider.client_secret_enc),
        scope=provider.scopes,
        redirect_uri=redirect_uri or _redirect_uri(provider.name, mode),
        code_challenge_method="S256",
    )
    verifier = generate_token(48)
    url, state = client.create_authorization_url(eps["authorize"], code_verifier=verifier)
    return url, state, verifier
```

Replace `fetch_identity` signature + client (lines 94-101):
```python
async def fetch_identity(provider: OAuthProvider, mode: str,
                         authorization_response: str, verifier: str,
                         redirect_uri: str | None = None) -> OAuthIdentity:
    eps = await _endpoints(provider)
    client = AsyncOAuth2Client(
        provider.client_id, decrypt_secret(provider.client_secret_enc),
        scope=provider.scopes,
        redirect_uri=redirect_uri or _redirect_uri(provider.name, mode),
        code_challenge_method="S256",
    )
```
(Leave the rest of `fetch_identity` unchanged.)

- [ ] **Step 4: Run helper + router suites**

Run: `cd backend && .venv/bin/python -m pytest tests/test_oauth_helpers.py tests/test_oauth_router.py -v`
Expected: PASS (existing callers pass `redirect_uri=None` implicitly → same behavior).

- [ ] **Step 5: Commit**

```bash
git add backend/app/security/oauth.py backend/tests/test_oauth_helpers.py
git commit -m "refactor(sso): optional redirect_uri override in oauth helpers"
```

---

## Task 7: Config-check endpoint

**Files:**
- Modify: `backend/app/schemas.py` (add result schemas)
- Modify: `backend/app/security/oauth.py` (add `discovery_checks`)
- Modify: `backend/app/routers/oauth_admin.py` (add endpoint)
- Test: `backend/tests/test_oauth_admin.py`

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_oauth_admin.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/test_oauth_admin.py::test_config_check_ok -v`
Expected: FAIL — 404 (endpoint not defined).

- [ ] **Step 3: Add schemas**

In `backend/app/schemas.py`, after `ProviderOut` (line 159) add:
```python
class ProviderTestCheck(BaseModel):
    label: str
    ok: bool
    detail: str = ""


class ProviderTestResult(BaseModel):
    ok: bool
    checks: list[ProviderTestCheck]
```

- [ ] **Step 4: Add the `discovery_checks` helper**

In `backend/app/security/oauth.py`, after `_endpoints` (line 73) add:
```python
async def discovery_checks(provider: OAuthProvider) -> tuple[bool, list[dict]]:
    """Server-side reachability/validity checks. Never raises."""
    checks: list[dict] = []
    checks.append({"label": "client_id set", "ok": bool(provider.client_id),
                   "detail": "" if provider.client_id else "missing"})
    try:
        eps = await _endpoints(provider)
        src = "discovery" if provider.kind == "oidc" else "config"
        for key in ("authorize", "token", "userinfo"):
            val = eps.get(key)
            checks.append({"label": f"{key} endpoint", "ok": bool(val),
                           "detail": val or f"missing in {src}"})
    except Exception as e:  # noqa: BLE001 — surface, never 500
        checks.append({"label": "endpoint discovery", "ok": False, "detail": str(e)})
    ok = all(c["ok"] for c in checks)
    return ok, checks
```

- [ ] **Step 5: Add the endpoint**

In `backend/app/routers/oauth_admin.py`: add imports at top —
```python
from app.schemas import ProviderTestResult
from app.security import oauth
```
Then after `update_provider` (line 65) add:
```python
@router.post("/{provider_id}/test/config", response_model=ProviderTestResult)
async def test_config(provider_id: str, admin: User = Depends(require_admin),
                      session: AsyncSession = Depends(get_session)):
    p = await session.get(OAuthProvider, provider_id)
    if not p:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    ok, checks = await oauth.discovery_checks(p)
    return ProviderTestResult(ok=ok, checks=checks)
```

- [ ] **Step 6: Run test to verify it passes**

Run: `cd backend && .venv/bin/python -m pytest tests/test_oauth_admin.py::test_config_check_ok -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add backend/app/schemas.py backend/app/security/oauth.py backend/app/routers/oauth_admin.py backend/tests/test_oauth_admin.py
git commit -m "feat(sso): provider config-check endpoint"
```

---

## Task 8: Test-login round-trip (no session)

**Files:**
- Modify: `backend/app/routers/oauth_admin.py` (add start + callback)
- Test: `backend/tests/test_oauth_admin.py`

> Reuses `oauth.build_authorize`/`fetch_identity` with an explicit `redirect_uri` to `…/test/callback`. Creates NO session and NO user/identity. The callback returns an HTML page that `postMessage`s the probe result to the opener.

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_oauth_admin.py`:

```python
@pytest.mark.asyncio
async def test_test_login_callback_probes_without_session(admin_client, monkeypatch):
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
    # no federated identity row created by a test
    from app.database import get_session  # noqa: F401
```

> If the test client doesn't expose `.cookies.set`, set the cookie via the request: `await admin_client.get(url, cookies={oauth.TX_COOKIE: tx})`. Match the pattern used elsewhere in this test module for cookie handling.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/test_oauth_admin.py::test_test_login_callback_probes_without_session -v`
Expected: FAIL — 404 (endpoints not defined).

- [ ] **Step 3: Add the endpoints**

In `backend/app/routers/oauth_admin.py` add imports —
```python
from fastapi import Request
from fastapi.responses import RedirectResponse, HTMLResponse
from app.config import Settings
import json as _json

_settings = Settings()
```
Add after `test_config`:
```python
def _test_redirect_uri(provider_id: str) -> str:
    return f"{_settings.oauth_redirect_base()}/api/oauth-providers/{provider_id}/test/callback"


@router.get("/{provider_id}/test/start")
async def test_start(provider_id: str, admin: User = Depends(require_admin),
                     session: AsyncSession = Depends(get_session)):
    p = await session.get(OAuthProvider, provider_id)
    if not p:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    redirect = _test_redirect_uri(provider_id)
    url, state, verifier = await oauth.build_authorize(p, mode="test", redirect_uri=redirect)
    resp = RedirectResponse(url, status_code=status.HTTP_302_FOUND)
    resp.set_cookie(oauth.TX_COOKIE,
                    oauth.pack_tx(p.name, state, verifier, "test", provider_id),
                    max_age=oauth.TX_TTL, httponly=True,
                    secure=_settings.COOKIE_SECURE, samesite="lax")
    return resp


def _probe_page(probe: dict) -> str:
    payload = _json.dumps(probe)
    return (
        "<!doctype html><html><body><script>"
        f"const r={payload};"
        "if(window.opener){window.opener.postMessage({type:'sso-test',result:r},'*');}"
        "document.body.innerText=JSON.stringify(r,null,2);"
        "setTimeout(()=>window.close(),500);"
        "</script></body></html>"
    )


@router.get("/{provider_id}/test/callback")
async def test_callback(provider_id: str, request: Request,
                        admin: User = Depends(require_admin),
                        session: AsyncSession = Depends(get_session)):
    p = await session.get(OAuthProvider, provider_id)
    if not p:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    tx_raw = request.cookies.get(oauth.TX_COOKIE)
    try:
        tx = oauth.unpack_tx(tx_raw or "")
    except Exception:
        return HTMLResponse(_probe_page({"ok": False, "error": "bad_state"}))
    if tx["mode"] != "test" or tx["uid"] != provider_id or \
            request.query_params.get("state") != tx["state"]:
        return HTMLResponse(_probe_page({"ok": False, "error": "state_mismatch"}))
    redirect = _test_redirect_uri(provider_id)
    try:
        identity = await oauth.fetch_identity(p, "test", str(request.url),
                                              tx["verifier"], redirect_uri=redirect)
    except Exception as e:  # noqa: BLE001
        return HTMLResponse(_probe_page({"ok": False, "error": str(e)}))
    would_pass = bool(identity.email) and (identity.email_verified or p.trust_email)
    probe = {"ok": True, "sub": identity.sub, "email": identity.email,
             "email_verified": identity.email_verified, "trust_email": p.trust_email,
             "would_pass": would_pass, "claims": identity.claims}
    resp = HTMLResponse(_probe_page(probe))
    resp.delete_cookie(oauth.TX_COOKIE)
    return resp
```

> No `_issue_session`, no `federation.*` calls here — a test never mutates auth state.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/bin/python -m pytest tests/test_oauth_admin.py::test_test_login_callback_probes_without_session -v`
Expected: PASS

- [ ] **Step 5: Run the full backend suite + lint**

Run: `cd backend && .venv/bin/python -m pytest -v && .venv/bin/python -m ruff check app/ tests/`
Expected: all PASS, ruff clean.

- [ ] **Step 6: Commit**

```bash
git add backend/app/routers/oauth_admin.py backend/tests/test_oauth_admin.py
git commit -m "feat(sso): test-login round-trip probe (no session/user mutation)"
```

---

## Task 9: Frontend API client — types + test methods

**Files:**
- Modify: `frontend/src/api/client.ts:11-20, 159, 164-169`

- [ ] **Step 1: Extend types**

Replace `OAuthProviderRow` (lines 11-15):
```typescript
export type OAuthProviderRow = {
  id: string; name: string; display_label: string; kind: string;
  issuer_url: string | null; client_id: string; scopes: string;
  role_map: Record<string, unknown>; enabled: boolean; has_secret: boolean;
  icon_url: string | null; trust_email: boolean;
};
```

Replace `OAuthProviderCreate` (lines 16-20):
```typescript
export type OAuthProviderCreate = {
  name: string; display_label: string; kind: string; issuer_url?: string;
  authorize_url?: string; token_url?: string; userinfo_url?: string;
  client_id: string; client_secret: string; scopes?: string;
  role_map?: Record<string, unknown>; icon_url?: string | null; trust_email?: boolean;
};

export type ProviderTestResult = {
  ok: boolean;
  checks: { label: string; ok: boolean; detail: string }[];
};
```

- [ ] **Step 2: Update public providers type + add test methods**

Replace line 159 (`oauthProviders: ...`):
```typescript
  oauthProviders: () => request<{ name: string; display_label: string; icon_url: string | null }[]>("/auth/oauth/providers"),
```

After `deleteOAuthProvider` (line 169) add:
```typescript
  testOAuthConfig: (id: string) =>
    request<ProviderTestResult>(`/oauth-providers/${id}/test/config`, { method: "POST" }),
  oauthTestStartUrl: (id: string) => `/api/oauth-providers/${id}/test/start`,
```

- [ ] **Step 3: Typecheck**

Run: `cd frontend && npm run lint`
Expected: PASS (no type errors).

- [ ] **Step 4: Commit**

```bash
git add frontend/src/api/client.ts
git commit -m "feat(sso): client types + provider test API methods"
```

---

## Task 10: Provider add/edit dialog component

**Files:**
- Create: `frontend/src/components/system/provider-dialog.tsx`

- [ ] **Step 1: Create the dialog component**

Create `frontend/src/components/system/provider-dialog.tsx`:

```tsx
import { useEffect, useRef, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  api, type OAuthProviderRow, type OAuthProviderCreate, type ProviderTestResult,
} from "@/api/client";
import { KeyRound, Upload, X, Check, AlertCircle, ChevronDown } from "lucide-react";

const MAX_ICON_BYTES = 200 * 1024;

const EMPTY: OAuthProviderCreate = {
  name: "", display_label: "", kind: "oidc", issuer_url: "",
  client_id: "", client_secret: "", scopes: "openid email profile",
  icon_url: null, trust_email: false,
};

type Props = {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  editing: OAuthProviderRow | null; // null = add mode
};

export function ProviderDialog({ open, onOpenChange, editing }: Props) {
  const qc = useQueryClient();
  const [form, setForm] = useState<OAuthProviderCreate>(EMPTY);
  const [advanced, setAdvanced] = useState(false);
  const [test, setTest] = useState<ProviderTestResult | null>(null);
  const [probe, setProbe] = useState<Record<string, unknown> | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!open) return;
    setTest(null);
    setProbe(null);
    if (editing) {
      setForm({
        name: editing.name, display_label: editing.display_label, kind: editing.kind,
        issuer_url: editing.issuer_url ?? "", client_id: editing.client_id,
        client_secret: "", scopes: editing.scopes,
        icon_url: editing.icon_url, trust_email: editing.trust_email,
      });
    } else {
      setForm(EMPTY);
    }
  }, [open, editing]);

  const set = (k: keyof OAuthProviderCreate) => (
    e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>
  ) => setForm((f) => ({ ...f, [k]: e.target.value }));

  function autoName(label: string) {
    if (editing) return; // name locked on edit
    const slug = label.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
    setForm((f) => ({ ...f, display_label: label, name: slug }));
  }

  function onPickIcon(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    if (file.size > MAX_ICON_BYTES) {
      toast.error("Icon too large (max 200KB)");
      return;
    }
    const reader = new FileReader();
    reader.onload = () => setForm((f) => ({ ...f, icon_url: String(reader.result) }));
    reader.readAsDataURL(file);
  }

  const save = useMutation({
    mutationFn: () => {
      if (editing) {
        const patch: Partial<OAuthProviderCreate> & { enabled?: boolean } = {
          display_label: form.display_label, issuer_url: form.issuer_url,
          client_id: form.client_id, scopes: form.scopes,
          icon_url: form.icon_url, trust_email: form.trust_email,
          authorize_url: form.authorize_url, token_url: form.token_url,
          userinfo_url: form.userinfo_url,
        };
        if (form.client_secret) patch.client_secret = form.client_secret;
        return api.updateOAuthProvider(editing.id, patch);
      }
      return api.createOAuthProvider(form);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["oauth-providers"] });
      toast.success(editing ? "Provider updated" : "Provider added");
      onOpenChange(false);
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const checkConfig = useMutation({
    mutationFn: () => api.testOAuthConfig(editing!.id),
    onSuccess: (r) => setTest(r),
    onError: (e: Error) => toast.error(e.message),
  });

  function testLogin() {
    if (!editing) return;
    const w = window.open(api.oauthTestStartUrl(editing.id), "sso-test",
      "width=520,height=640");
    const onMsg = (ev: MessageEvent) => {
      if (ev.data?.type === "sso-test") {
        setProbe(ev.data.result);
        window.removeEventListener("message", onMsg);
        w?.close();
      }
    };
    window.addEventListener("message", onMsg);
  }

  const canSave = form.display_label && form.name && form.client_id &&
    (editing || form.client_secret) &&
    (form.kind !== "oidc" || form.issuer_url);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{editing ? "Edit provider" : "Add SSO provider"}</DialogTitle>
          <DialogDescription>
            Connect an identity provider so users can sign in with single sign-on.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-3">
          <Field label="Display name" hint="Shown to users on the login button.">
            <Input value={form.display_label}
                   onChange={(e) => autoName(e.target.value)}
                   placeholder="My Authentik" />
          </Field>
          <Field label="Internal name" hint="Lowercase id used in URLs. Locked after creation.">
            <Input value={form.name} onChange={set("name")} disabled={!!editing}
                   placeholder="authentik" />
          </Field>
          <Field label="Type">
            <select className="w-full rounded-md border border-border bg-background p-2 text-sm"
                    value={form.kind} onChange={set("kind")} disabled={!!editing}>
              <option value="oidc">OIDC — Authentik, Google, Keycloak, generic</option>
              <option value="oauth2">OAuth2 — GitHub</option>
            </select>
          </Field>
          {form.kind === "oidc" && (
            <Field label="Issuer URL" hint="We auto-discover endpoints from here.">
              <Input value={form.issuer_url || ""} onChange={set("issuer_url")}
                     placeholder="https://auth.example.com/application/o/styx/" />
            </Field>
          )}
          <Field label="Client ID">
            <Input value={form.client_id} onChange={set("client_id")} />
          </Field>
          <Field label="Client secret"
                 hint={editing ? "Leave blank to keep the current secret." : undefined}>
            <Input type="password" value={form.client_secret} onChange={set("client_secret")}
                   placeholder={editing ? "•••• unchanged" : ""} />
          </Field>
          <Field label="Scopes">
            <Input value={form.scopes || ""} onChange={set("scopes")} />
          </Field>

          <Field label="Icon" hint="URL or upload. Shown on the login button.">
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-md border border-border bg-muted/40 overflow-hidden">
                {form.icon_url
                  ? <img src={form.icon_url} alt="" className="h-6 w-6 object-contain" />
                  : <KeyRound className="h-4 w-4 text-muted-foreground" />}
              </div>
              <Input value={form.icon_url ?? ""} placeholder="https://…/logo.svg"
                     onChange={(e) => setForm((f) => ({ ...f, icon_url: e.target.value || null }))} />
              <input ref={fileRef} type="file" accept="image/*" hidden onChange={onPickIcon} />
              <Button type="button" variant="outline" size="sm"
                      onClick={() => fileRef.current?.click()}>
                <Upload className="h-4 w-4" />
              </Button>
              {form.icon_url && (
                <Button type="button" variant="ghost" size="sm"
                        onClick={() => setForm((f) => ({ ...f, icon_url: null }))}>
                  <X className="h-4 w-4" />
                </Button>
              )}
            </div>
          </Field>

          <label className="flex items-start gap-3 rounded-md border border-border p-3 cursor-pointer">
            <input type="checkbox" checked={!!form.trust_email} className="mt-0.5 h-4 w-4"
                   onChange={(e) => setForm((f) => ({ ...f, trust_email: e.target.checked }))} />
            <span className="text-sm">
              <span className="font-medium">Trust emails from this provider</span>
              <span className="block text-xs text-muted-foreground">
                Enable if your IdP (e.g. Authentik) doesn't send a verified-email claim.
                Email is still required.
              </span>
            </span>
          </label>

          <button type="button" onClick={() => setAdvanced((v) => !v)}
                  className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground">
            <ChevronDown className={`h-3 w-3 transition-transform ${advanced ? "rotate-180" : ""}`} />
            Advanced — manual endpoint overrides
          </button>
          {advanced && (
            <div className="space-y-2 rounded-md border border-border p-3">
              <Input placeholder="authorize_url" value={form.authorize_url || ""} onChange={set("authorize_url")} />
              <Input placeholder="token_url" value={form.token_url || ""} onChange={set("token_url")} />
              <Input placeholder="userinfo_url" value={form.userinfo_url || ""} onChange={set("userinfo_url")} />
            </div>
          )}

          {editing && (
            <div className="flex gap-2">
              <Button type="button" variant="outline" size="sm"
                      onClick={() => checkConfig.mutate()} disabled={checkConfig.isPending}>
                {checkConfig.isPending ? "Checking…" : "Check config"}
              </Button>
              <Button type="button" variant="outline" size="sm" onClick={testLogin}>
                Test login
              </Button>
            </div>
          )}
          {!editing && (
            <p className="text-xs text-muted-foreground">Save the provider to enable Check config / Test login.</p>
          )}

          {test && (
            <div className="space-y-1 rounded-md border border-border p-3 text-xs">
              {test.checks.map((c) => (
                <div key={c.label} className="flex items-center gap-2">
                  {c.ok ? <Check className="h-3 w-3 text-success" />
                        : <AlertCircle className="h-3 w-3 text-destructive" />}
                  <span className="font-medium">{c.label}</span>
                  <span className="text-muted-foreground truncate">{c.detail}</span>
                </div>
              ))}
            </div>
          )}
          {probe && (
            <div className="rounded-md border border-border p-3 text-xs">
              <div className={probe.would_pass ? "text-success" : "text-destructive"}>
                {probe.would_pass ? "✓ A real login would succeed" : "✗ A real login would be rejected"}
              </div>
              <pre className="mt-2 max-h-40 overflow-auto whitespace-pre-wrap text-muted-foreground">
                {JSON.stringify(probe, null, 2)}
              </pre>
            </div>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button onClick={() => save.mutate()} disabled={!canSave || save.isPending}>
            {save.isPending ? "Saving…" : editing ? "Save changes" : "Add provider"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function Field({ label, hint, children }: {
  label: string; hint?: string; children: React.ReactNode;
}) {
  return (
    <div className="space-y-1">
      <label className="block text-xs font-medium text-muted-foreground">{label}</label>
      {children}
      {hint && <p className="text-[11px] text-muted-foreground">{hint}</p>}
    </div>
  );
}
```

- [ ] **Step 2: Typecheck**

Run: `cd frontend && npm run lint`
Expected: PASS. (Fix any import/type errors before continuing. If `text-success` class is undefined in the theme, the build still passes — it's resolved in Task 11's manual check.)

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/system/provider-dialog.tsx
git commit -m "feat(sso): add/edit provider dialog with icon, trust, test tools"
```

---

## Task 11: Wire dialog into the providers panel

**Files:**
- Modify: `frontend/src/components/system/oauth-providers-panel.tsx` (full rewrite — slimmer)

- [ ] **Step 1: Rewrite the panel to use the dialog**

Replace the entire contents of `frontend/src/components/system/oauth-providers-panel.tsx`:

```tsx
import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, type OAuthProviderRow } from "@/api/client";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Shield, Plus, KeyRound } from "lucide-react";
import { ProviderDialog } from "./provider-dialog";

export function OAuthProvidersPanel() {
  const qc = useQueryClient();
  const { data: providers = [] } = useQuery({
    queryKey: ["oauth-providers"],
    queryFn: api.listOAuthProviders,
  });
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editing, setEditing] = useState<OAuthProviderRow | null>(null);

  const toggle = useMutation({
    mutationFn: (p: { id: string; enabled: boolean }) =>
      api.updateOAuthProvider(p.id, { enabled: p.enabled }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["oauth-providers"] }),
  });
  const remove = useMutation({
    mutationFn: (id: string) => api.deleteOAuthProvider(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["oauth-providers"] }),
  });

  function openAdd() { setEditing(null); setDialogOpen(true); }
  function openEdit(p: OAuthProviderRow) { setEditing(p); setDialogOpen(true); }

  return (
    <div className="space-y-6">
      <Card className="styx-card">
        <CardHeader className="pb-4">
          <div className="flex items-center justify-between gap-3">
            <div className="flex items-center gap-3">
              <div className="rounded-lg bg-primary/10 p-2">
                <Shield className="h-5 w-5 text-primary" />
              </div>
              <div>
                <CardTitle>OAuth / SSO providers</CardTitle>
                <CardDescription>Configure identity providers for federated authentication</CardDescription>
              </div>
            </div>
            <Button onClick={openAdd} size="sm">
              <Plus className="h-4 w-4" /> Add provider
            </Button>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          {providers.length === 0 ? (
            <div className="rounded-lg border border-dashed border-border p-8 text-center text-sm text-muted-foreground">
              No providers yet. Click <span className="font-medium">Add provider</span> to connect Authentik, Google, GitHub, or any OIDC provider.
            </div>
          ) : (
            <div className="border border-border rounded-lg overflow-hidden">
              <table className="w-full text-sm">
                <thead className="border-b border-border bg-muted/40">
                  <tr>
                    <th className="px-4 py-3 text-left font-semibold">Provider</th>
                    <th className="px-4 py-3 text-left font-semibold">Kind</th>
                    <th className="px-4 py-3 text-left font-semibold">Enabled</th>
                    <th className="px-4 py-3 text-right font-semibold">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {providers.map((p) => (
                    <tr key={p.id} className="border-b border-border hover:bg-muted/30 transition-colors">
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-2.5 font-medium">
                          <span className="flex h-7 w-7 items-center justify-center rounded-md border border-border bg-muted/40 overflow-hidden">
                            {p.icon_url
                              ? <img src={p.icon_url} alt="" className="h-4 w-4 object-contain" />
                              : <KeyRound className="h-3.5 w-3.5 text-muted-foreground" />}
                          </span>
                          {p.display_label}{" "}
                          <span className="text-muted-foreground">({p.name})</span>
                        </div>
                      </td>
                      <td className="px-4 py-3">
                        <span className="inline-flex items-center rounded-full bg-secondary/10 px-2.5 py-1 text-xs font-medium text-secondary-foreground">
                          {p.kind}
                        </span>
                      </td>
                      <td className="px-4 py-3">
                        <input type="checkbox" checked={p.enabled}
                               onChange={(e) => toggle.mutate({ id: p.id, enabled: e.target.checked })}
                               className="h-4 w-4 rounded cursor-pointer" />
                      </td>
                      <td className="px-4 py-3 text-right">
                        <Button variant="ghost" size="sm" onClick={() => openEdit(p)}>Edit</Button>
                        <Button variant="ghost" size="sm" onClick={() => remove.mutate(p.id)}
                                disabled={remove.isPending}
                                className="text-destructive hover:text-destructive hover:bg-destructive/10">
                          Delete
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      <ProviderDialog open={dialogOpen} onOpenChange={setDialogOpen} editing={editing} />
    </div>
  );
}
```

- [ ] **Step 2: Typecheck + build**

Run: `cd frontend && npm run lint && npm run build`
Expected: both PASS.

- [ ] **Step 3: Manual verification**

Start backend (`cd backend && .venv/bin/python -m uvicorn app.main:app --reload --port 8000`) and frontend (`cd frontend && npm run dev`). As admin → Settings → OAuth/SSO providers:
- "Add provider" opens the modal; OIDC preselected, scopes prefilled.
- Add an Authentik provider with issuer URL + client id/secret + **Trust emails** checked. Saves, appears in table with icon slot.
- Row "Edit" reopens modal pre-filled; secret shows "•••• unchanged"; saving without secret keeps it (table still shows enabled).
- In edit mode, "Check config" lists endpoint checks; "Test login" opens a popup.
Confirm no console errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/system/oauth-providers-panel.tsx
git commit -m "feat(sso): modal-based provider add/edit with icons + empty state"
```

---

## Task 12: Login-page provider icons

**Files:**
- Modify: `frontend/src/pages/LoginPage.tsx:13, 18, 64-81`

- [ ] **Step 1: Update provider state type + render icons**

In `frontend/src/pages/LoginPage.tsx`:

Replace line 13:
```tsx
  const [providers, setProviders] = useState<{ name: string; display_label: string; icon_url: string | null }[]>([]);
```

Add the import (top of file, with other lucide imports — add a new import line):
```tsx
import { KeyRound } from "lucide-react";
```

Replace the provider button block (lines 66-74):
```tsx
              {providers.map((p) => (
                <a
                  key={p.name}
                  href={api.oauthStartUrl(p.name)}
                  className="flex w-full items-center justify-center gap-2 rounded-md border border-border bg-background p-2.5 text-sm font-medium hover:bg-accent"
                >
                  {p.icon_url
                    ? <img src={p.icon_url} alt="" className="h-5 w-5 object-contain" />
                    : <KeyRound className="h-4 w-4 text-muted-foreground" />}
                  Continue with {p.display_label}
                </a>
              ))}
```

- [ ] **Step 2: Typecheck + build**

Run: `cd frontend && npm run lint && npm run build`
Expected: both PASS.

- [ ] **Step 3: Manual verification**

Reload `/login`. The Authentik button shows its icon (or a key fallback if no icon set) left of "Continue with …". Click it → with **Trust emails** enabled on the provider, Authentik login now completes instead of erroring "Your identity provider did not confirm a verified email."

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/LoginPage.tsx
git commit -m "feat(sso): render provider icons on login page"
```

---

## Final Verification

- [ ] **Backend:** `cd backend && .venv/bin/python -m pytest -v && .venv/bin/python -m ruff check app/ tests/` — all pass, lint clean.
- [ ] **Frontend:** `cd frontend && npm run lint && npm run build` — pass.
- [ ] **End-to-end (manual):** Configure Authentik provider with Trust emails on → log in via the login-page button → lands on dashboard. Without Trust emails (and Authentik omitting `email_verified`) → still rejected as expected. Edit a provider, re-test config, confirm icon shows on login page.
- [ ] **CSP note:** If provider icons (remote `https:` or `data:` URIs) don't render, check the CSP `img-src` directive (security headers middleware) allows `https:` and `data:`. Adjust if needed and note it in the commit.

---

## Self-Review Notes (author)

- **Spec coverage:** modal add/edit (T10–11), edit existing (T10–11), test provider both config+login (T7–8, T10), icon url+upload (T1,T2,T4,T10), login-page icons (T5,T12), verified-email fix via trust_email (T1–T4 schema/persist, T3 gate, T8 probe shows would_pass). All covered.
- **Type consistency:** `icon_url`/`trust_email` names identical across model, schemas, client types, components. `discovery_checks` / `ProviderTestResult` / `ProviderTestCheck` consistent T7↔T9↔T10. `oauthTestStartUrl`/`testOAuthConfig` defined T9, used T10.
- **Known dependency:** Task 2 and Task 4 both touch `_out`; Task 2 note instructs applying the `_out` change there so its test is green — Task 4 then adds only create/update logic. Do them in order.
- **IdP redirect URI:** test-login uses `…/test/callback` — the operator must register that redirect URI at the IdP, else the round-trip test fails (config-check still works). Surface this in the UI helper if a tester reports redirect_uri mismatch.
