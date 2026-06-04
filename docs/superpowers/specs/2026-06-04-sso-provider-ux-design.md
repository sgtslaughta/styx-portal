# SSO Provider UX Polish + Verified-Email Fix — Design

Date: 2026-06-04
Status: Approved (pending spec review)
Scope: Admin SSO provider management UI, provider icons, provider testing, OIDC verified-email handling.

## Problem

1. **Verified-email bug:** Logging in via Authentik (generic OIDC) fails with "Your identity provider did not confirm a verified email." Authentik's userinfo often omits the `email_verified` claim; backend defaults it to `False` and rejects.
2. **Provider admin UX is thin:** add-only inline form, no edit, no test, no icons. Hard for new users to configure correctly.

## Goals

- Fix the verified-email rejection without blindly trusting every IdP.
- Make provider config a modal (add + edit) that a new user can complete confidently.
- Let an admin test a provider after adding it (config validation + real login round-trip).
- Support a custom icon per provider (paste URL or upload), shown on the login page.

## Non-Goals

- Role/group mapping UI (`role_map` stays API-only for now).
- JWKS / id_token signature verification (identity still comes from userinfo endpoint).
- Multi-host icon file storage / CDN.

---

## 1. Data Model

`OAuthProvider` (`backend/app/models.py`) gains two columns:

| Column | Type | Default | Purpose |
|--------|------|---------|---------|
| `icon_url` | `str \| None` | `None` | Provider icon. Either a remote URL (`https://…/logo.svg`) or an inline base64 data URI (`data:image/png;base64,…`) from upload. |
| `trust_email` | `bool` | `False` | When true, a missing/false `email_verified` claim is treated as verified for this provider. |

Migration: append to the list in `database.py::_run_migrations`:

```python
("oauth_providers", "icon_url", "TEXT"),
("oauth_providers", "trust_email", "BOOLEAN"),
```

(Idempotent ALTER TABLE pattern already in use. Existing rows get `NULL`/`0`; `trust_email` falsy = current strict behavior preserved.)

## 2. Schemas (`backend/app/schemas.py`)

- `ProviderCreate`: add `icon_url: str | None = None`, `trust_email: bool = False`.
- `ProviderUpdate`: add `icon_url: str | None = None`, `trust_email: bool | None = None`.
- `ProviderOut`: add `icon_url: str | None`, `trust_email: bool`.
- Public list response (`/api/auth/oauth/providers`, in `routers/oauth.py`) extends from `{name, display_label}` to also include `icon_url`. (No secrets exposed.)

**Icon validation** (in create/update handlers): if `icon_url` is a data URI, enforce max length ~256KB and an allowed `image/*` mime prefix; reject otherwise with 422. Remote URLs accepted as-is (rendered in an `<img>`, no server fetch).

## 3. Verified-Email Fix

`backend/app/security/oauth.py` — no behavior change in `normalize_oidc`; still reads `email_verified` (default `False`). Trust decision lives in federation, where the provider record is available.

`backend/app/services/federation.py`:

```python
async def resolve_identity(session, provider_name, identity, role_map=None,
                           trust_email=False):
    if not identity.email:
        raise EmailUnverified("IdP did not provide an email")
    if not identity.email_verified and not trust_email:
        raise EmailUnverified("IdP did not provide a verified email")
    ...

async def link_identity(session, user, provider_name, identity, trust_email=False):
    if not identity.email_verified and not trust_email:
        raise EmailUnverified("IdP did not provide a verified email")
    ...
```

Callers in `routers/oauth.py` and `routers/auth.py` pass `provider.trust_email`. Email is always required; only the *verified* gate is relaxable per-provider.

## 4. Provider Testing (Both)

New admin-only endpoints in `routers/oauth_admin.py`.

### 4a. Config check — `POST /api/oauth-providers/{id}/test/config`

Server-side, no browser. Returns a checklist:

```json
{ "ok": true,
  "checks": [
    {"label": "Discovery document", "ok": true,  "detail": "200 from issuer/.well-known/openid-configuration"},
    {"label": "authorize endpoint",  "ok": true,  "detail": "https://idp/authorize"},
    {"label": "token endpoint",      "ok": true,  "detail": "https://idp/token"},
    {"label": "userinfo endpoint",   "ok": true,  "detail": "https://idp/userinfo"},
    {"label": "client_id set",       "ok": true,  "detail": ""}
  ]
}
```

- OIDC: fetch `{issuer_url}/.well-known/openid-configuration`, confirm 200 + required endpoints present.
- OAuth2: confirm explicit `authorize_url`/`token_url`/`userinfo_url` are set and host-reachable (HEAD/GET, non-5xx).
- Always: `client_id` non-empty. `ok` is AND of all checks. Network errors → that check `ok:false` with the error string in `detail` (never 500).

### 4b. Test login — `GET …/test/start` + `GET …/test/callback`

A real OAuth round-trip that **issues no session and creates/links no user**.

- `test/start`: same authorize redirect as the live flow, but state cookie marks `mode=test` and the redirect_uri points at `test/callback`.
- `test/callback`: exchange code, `fetch_identity`, then return an HTML page that `postMessage`s the result to the opener and closes:

```json
{ "ok": true,
  "sub": "ak-uuid",
  "email": "user@example.com",
  "email_verified": false,
  "trust_email": true,
  "would_pass": true,
  "claims": { "...": "raw userinfo" } }
```

`would_pass = bool(email) and (email_verified or trust_email)`. This directly shows an admin why a real login would be rejected — the diagnostic for the Authentik issue.

Reuses existing `oauth.fetch_identity`; the only new logic is the no-session test branch and result page.

## 5. Frontend — Provider Dialog

Split `components/system/oauth-providers-panel.tsx` (keep <500 lines):
- `oauth-providers-panel.tsx` — list/table, enable toggle, delete, "Add provider" button, "Edit" per row.
- `provider-dialog.tsx` — the add/edit modal (new file).

Modal uses existing `components/ui/dialog.tsx` (Radix + framer-motion). Same component for add (empty) and edit (pre-filled from row; `has_secret` true → secret field placeholder "•••• unchanged", blank submit keeps existing secret).

**Fields (top → bottom):**
1. Display label (required) — friendly, shown to users.
2. Name (required, slug) — lowercase id used in URLs; auto-suggested from label, locked on edit.
3. Kind — OIDC (default) / OAuth2, with one-line helper each.
4. Issuer URL — shown for OIDC; helper "We auto-discover endpoints from here."
5. Client ID, Client secret.
6. Scopes — prefilled `openid email profile`.
7. **Icon** — URL text input + "Upload" button; live preview swatch; clear button.
8. **Trust emails toggle** — label "Trust emails from this provider", help "Enable if your IdP (e.g. Authentik) doesn't send a verified-email claim."
9. **Advanced (collapsible)** — `authorize_url`, `token_url`, `userinfo_url` overrides (for OAuth2 / non-discovery).

**Modal actions:** `[Check config]` `[Test login]` `[Cancel]` `[Save]`.
- Check config: calls 4a, renders the checklist inline (green/red rows). Enabled after save (needs a persisted id) — for a new unsaved provider, prompt "Save first to test".
- Test login: opens 4b in a popup, listens for `postMessage`, renders the returned identity + `would_pass` banner inline.

New-user ease: OIDC preselected, scopes prefilled, inline helpers, required-field validation before Save, errors surfaced from the API response.

## 6. Frontend — Icon Upload

In `provider-dialog.tsx`: hidden `<input type="file" accept="image/*">`; on pick, `FileReader.readAsDataURL` → set `icon_url` to the data URI. Guard: reject > ~200KB pre-encode with a toast. Preview renders the current `icon_url` (URL or data URI) in a 32px rounded box; clear button resets to `null`.

## 7. Frontend — Login Page Icons

`pages/LoginPage.tsx`: each provider button renders, left of the text, `icon_url` in a 20px `<img>` when present; otherwise a lucide `KeyRound` fallback. `api/client.ts` `oauthProviders()` return type gains `icon_url?: string | null`. Provider-management API types in `client.ts` gain `icon_url` + `trust_email` on create/update/out.

---

## Files Touched

Backend:
- `app/models.py` — 2 columns.
- `app/database.py` — 2 migration rows.
- `app/schemas.py` — create/update/out fields.
- `app/services/federation.py` — trust_email gate.
- `app/routers/oauth.py` — pass trust_email; public list adds icon_url.
- `app/routers/oauth_admin.py` — icon validation; test/config + test/start + test/callback endpoints; pass trust_email on link path if applicable.
- `app/routers/auth.py` — pass trust_email into link_identity.

Frontend:
- `src/components/system/oauth-providers-panel.tsx` — list + buttons (slimmed).
- `src/components/system/provider-dialog.tsx` — NEW modal.
- `src/api/client.ts` — types + test endpoints.
- `src/pages/LoginPage.tsx` — provider icons.

## Testing

- **Verified-email:** unit tests on `resolve_identity`/`link_identity` — (email_verified F + trust F) rejects; (F + trust T) passes; (T + trust F) passes; (no email) always rejects.
- **Schemas/migration:** provider create/update round-trips `icon_url` + `trust_email`; `ProviderOut.has_secret` still hides secret; data-URI size guard rejects oversize.
- **Config test endpoint:** mock httpx — discovery 200 → all checks ok; discovery 404 / network error → `ok:false`, no 500.
- **Test-login callback:** mock `fetch_identity` → returns identity JSON with correct `would_pass`; asserts NO session cookie set and NO user/identity row created.
- **Public providers list:** includes `icon_url`, excludes secrets.
- Frontend: existing test approach (if any) for the panel; otherwise manual verification of modal add/edit/test + login-page icon render.

## Risks / Notes

- `trust_email` defaults false → no security regression for existing providers; admin opts in knowingly. Helper text states the trade-off.
- Test-login popup must share the same registered redirect_uri family at the IdP; document that `…/test/callback` may need to be added as an allowed redirect URI in the IdP (or reuse one callback with a `mode` in state — chosen: separate path, clearer). If IdP redirect allow-list is strict, config-check still works without it.
- Remote icon URLs are rendered, not proxied; a broken/blocked URL just shows the fallback icon. CSP `img-src` may need to allow `data:` and `https:` (verify current policy).
