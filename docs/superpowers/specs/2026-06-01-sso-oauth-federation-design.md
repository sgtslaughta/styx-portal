# SSO / OAuth Federation — Design

Date: 2026-06-01
Status: Approved (Phase 2 of the auth/security overhaul; builds on Phase 1 native auth)

## Context

Phase 1 (merged `main` 969c8cf) added native JWT auth with per-user ownership and an
admin-invite-only model. The original requirements always wanted SSO; Phase 1 chose a
**hybrid** design specifically so federation could be added later on the same `User`
table. An Authentik ForwardAuth stub exists (`traefik/dynamic.yml.tmpl`,
`config.AUTHENTIK_MIDDLEWARE`) but is unused and is **not** the chosen path.

This phase adds in-app OIDC/OAuth login: users sign in with an external IdP, the backend
verifies the identity and mints the **same** Phase-1 cookie session. SSO is a
login/provision method, not a parallel auth system.

### Locked decisions (with user)
| Topic | Decision |
|-------|----------|
| Integration | In-app OIDC/OAuth (authlib); backend runs the code flow and mints Phase-1 cookies |
| Provider config | DB table, client secrets Fernet-encrypted; admins CRUD via admin UI |
| Provisioning | Pre-authorized only: SSO succeeds only if verified email matches an existing user or an open invite; no silent signup |
| Providers (first) | Generic OIDC (issuer discovery) + Google (OIDC) + GitHub (OAuth2) |
| Account linking | Included now: logged-in users link/unlink providers in account settings (keep ≥1 login method); plus automatic link when SSO verified-email matches an existing user |
| Secrets key | Fernet key derived from `JWT_SECRET` via HKDF (no new env var; rotating `JWT_SECRET` requires re-entering provider secrets — documented) |

## Architecture

```
GET /auth/oauth/{name}/start
   → build authorize URL (state + PKCE + nonce), set short-lived signed httpOnly state cookie
   → redirect to IdP
IdP login → GET /auth/oauth/{name}/callback?code&state
   → validate state cookie; exchange code (PKCE); fetch + verify userinfo/id_token (nonce)
   → require verified email (reject otherwise)
   → federation.resolve():
        FederatedIdentity(provider,sub) exists      → that User           (login)
        else verified email == existing User.email   → create FederatedIdentity (LINK)
        else verified email ∈ open Invite            → create User+identity, mark invite used (PROVISION)
        else                                          → 403 not authorized
   → reject if User.is_active is false
   → _issue_session(...)  # identical Phase-1 cookies (access/refresh/csrf)
```

Identity resolution lives in one service so the policy is testable in isolation. The
OAuth protocol mechanics live in `oauth.py`; routers stay thin.

## Data model (new)

```
OAuthProvider:
  id, name (unique, e.g. "google" | "github" | "authentik"),
  display_label, kind ("oidc" | "oauth2"),
  issuer_url (oidc) | authorize_url + token_url + userinfo_url (oauth2),
  client_id, client_secret_enc (Fernet ciphertext),
  scopes (str), role_map (JSON: {"claim": "groups", "values": {"selkies-admins": "admin"}}),
  enabled (bool), created_at, updated_at

FederatedIdentity:
  id, user_id (FK users.id), provider (name), subject (IdP "sub"),
  email, created_at
  UNIQUE(provider, subject)
```

`User` is unchanged. A native-password user and any number of federated identities all
point at one `User`. No migration to existing tables beyond creating these two.

## Components (each <500 lines, one responsibility)

| File | Responsibility |
|------|----------------|
| `app/security/crypto.py` | `encrypt_secret`/`decrypt_secret` (Fernet); module key = HKDF-SHA256(`JWT_SECRET`, info="oauth-secret-enc"); fail-fast if `JWT_SECRET` unset |
| `app/security/oauth.py` | authlib client per `OAuthProvider`; `build_authorize(provider, redirect_uri)` → (url, state, verifier, nonce); `fetch_identity(provider, code, ...)` → normalized `OAuthIdentity{sub, email, email_verified, claims}`; GitHub special-case (`/user` + `/user/emails`, primary verified) |
| `app/services/federation.py` | `resolve_identity(session, provider_name, identity) -> User`: link/provision/reject + pre-authorized gate + role_map; raises typed errors (NotAuthorized, EmailUnverified, Disabled) |
| `app/routers/oauth.py` | `GET /auth/oauth/providers` (public: enabled name+label list), `GET /auth/oauth/{name}/start`, `GET /auth/oauth/{name}/callback` |
| `app/routers/oauth_admin.py` | admin CRUD `/api/oauth-providers` (list/create/update/delete/enable); responses NEVER include the secret (write-only; expose `has_secret` bool) |
| extend `app/routers/auth.py` | `GET /auth/link/{name}/start` + `GET /auth/link/{name}/callback` (link to current user), `DELETE /auth/link/{name}` (unlink; refuse if it would leave the user with no password and no other identity) |
| extend `app/config.py` | `OAUTH_REDIRECT_BASE` (default `https://{DOMAIN}`) |
| extend `app/main.py` | register `oauth` + `oauth_admin` routers; extend the boot guard so HKDF key derivation is exercised (already fail-fast on `JWT_SECRET`) |

### Provider specifics
- **Generic OIDC** — `{issuer}/.well-known/openid-configuration` discovery; scopes `openid email profile`; validate `id_token` (signature via JWKS, `nonce`, `aud`, `exp`); `sub`, `email`, `email_verified`, `groups` (if present) from claims.
- **Google** — OIDC via Google discovery; honors `email_verified`.
- **GitHub** — OAuth2 (no OIDC id_token): exchange code, `GET /user` (→ `sub` = id), `GET /user/emails` → choose the entry with `primary && verified`; if none verified → reject.

## Security

- **Verified email only** — reject when `email_verified` is false (OIDC) or no primary-verified email (GitHub). Prevents account-takeover by linking via a spoofable address.
- **Primary key = (provider, sub)** — email is used only to first-link/provision, never as the durable identity key.
- **CSRF/replay on the flow** — `state` (signed, short-lived httpOnly cookie) + PKCE (`S256`) + OIDC `nonce`; callback validates all three. authlib enforces token validation.
- **Pre-authorized gate** — provisioning requires a matching open (unused, unexpired) invite; otherwise 403. SSO never creates an account silently.
- **Disabled users** — `is_active=false` rejects SSO login too.
- **Secret at rest** — `client_secret` stored Fernet-encrypted; admin API is write-only for it.
- **Unlink safety** — refuse to unlink the last remaining login method (would lock the user out).
- **Rate limiting** — `/auth/oauth/*` falls under the Phase-1 `/auth/*` strict bucket.
- **Open-redirect** — redirect target is server-derived from `OAUTH_REDIRECT_BASE` + fixed callback path, never from a request parameter.

## Role assignment
On provision: start from the invite's role. Then apply the provider's optional `role_map`
(e.g. OIDC `groups` claim contains a configured value → `admin`); if nothing matches,
keep `user`. Linking to an existing user never changes that user's role.

## Frontend

- **Login/Setup pages** — fetch `/auth/oauth/providers`; render "Sign in with {label}"
  buttons that navigate to `/api/auth/oauth/{name}/start`. After the IdP round-trip the
  callback redirects back into the app; `useAuth().refresh()` picks up the session.
- **Admin → OAuth Providers panel** (System tab, admin-only) — list/add/edit/enable/
  disable providers; secret is a write-only field showing "set/unset"; edit scopes and
  role map.
- **Account settings → Connected accounts** — logged-in user links a provider (runs the
  link OAuth flow) or unlinks one (disabled when it is the last login method). Reuses the
  central `api/client.ts` wrapper.

## Error handling
- IdP/userinfo failures, bad state, unverified email, not-authorized, disabled → redirect
  to `/login?error=<code>` with a friendly message (no internal detail leaked).
- Admin CRUD validation (bad issuer, missing client_id) → 400 with field message.
- Unlink-last-method → 400.

## Testing
Mock the IdP — no live network. Patch `oauth.fetch_identity` / authlib client to return
canned identities. Cases:
- `(provider, sub)` hit → login as that user.
- verified email matches existing user → links (FederatedIdentity created), logs in.
- verified email matches open invite → provisions (role from invite/role_map), invite marked used.
- not pre-authorized → 403.
- unverified email → reject.
- disabled user → reject.
- GitHub primary-verified-email selection (and reject when none verified).
- `role_map` maps a group claim → admin.
- admin CRUD: create/list/update/enable; secret never returned; `has_secret` correct.
- crypto: encrypt→decrypt round-trip; HKDF key stable for a given `JWT_SECRET`.
- link/unlink: link adds identity; unlink refuses last login method.
- existing 110 backend tests stay green.

## Out of scope (future phases)
SCIM / auto-deprovision · per-device session management · social-account merge UI ·
admin-approval signup queue (superseded by pre-authorized-only).

## Critical files to reuse
- `backend/app/routers/auth.py` `_issue_session` / `_set_auth_cookies` — SSO mints the same session.
- `backend/app/security/deps.py` `get_current_user` / `require_admin` — guard link + admin routes.
- `backend/app/models.py` — `User`, `Invite` patterns; add the two new tables alongside.
- `backend/app/config.py` `jwt_secret_or_raise` + `main.py` boot guard — extend for HKDF key.
- `frontend/src/api/client.ts`, `src/auth/AuthContext.tsx`, `src/components/system/users-panel.tsx` — patterns for the new admin panel + login buttons + settings page.
- `backend/tests/conftest.py` `admin_client` fixture — base for SSO/admin tests.
