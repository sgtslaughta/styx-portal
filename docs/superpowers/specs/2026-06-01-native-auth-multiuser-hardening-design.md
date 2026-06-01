# Native Auth + Multi-User + Security Hardening — Design

Date: 2026-06-01
Status: Approved (Phase 1 of a multi-phase security overhaul)

## Context

Selkies Hub is internet-exposed (Cloudflare tunnel → Traefik → FastAPI/React) with
**zero enforced authentication**. An admin token is generated and logged on startup
(`backend/app/main.py:69-78`) but never validated; every API route is open to anyone who
reaches it. There is no user model, no sessions, no login page, permissive CORS
(`allow_methods/headers=["*"]`, `main.py:200-206`), and no security headers, CSRF, or rate
limiting. A 2026-05-24 spec chose Authentik ForwardAuth at the proxy layer but it was
never wired up.

This phase makes the app safe to expose: backend-owned identity (native JWT login),
per-user ownership of instances/templates, role-based access (admin/user), and baseline
security hardening to industry standard.

### Deferred to later phases (NOT this design)
SSO/OAuth/OIDC federation (Authentik, Google) · admin tuneable system settings/controls ·
admin metrics dashboard · email verification · captcha. Hooks are left in place
(`User` table is the federation join point; `owner_id` and role enforcement support later
admin UIs) but none are built here.

## Locked decisions

| Topic | Decision |
|-------|----------|
| Auth model | Hybrid — native JWT now, OAuth/OIDC federation later on the same `User` table |
| Isolation | Per-user ownership: `owner_id` on Instance/Template; admin sees all |
| Token transport | JWT in httpOnly + Secure + SameSite=Strict cookies + double-submit CSRF |
| Bootstrap | First-run setup wizard; `/auth/setup` unlocked only while 0 users exist |
| Registration | Admin invite-only — single-use, expiring invite tokens; no public signup |
| Libraries | `pyjwt` + `argon2-cffi` (Argon2id); stdlib `secrets` for CSRF/invite tokens |

## Architecture

```
Browser ──cookie(access 15m / refresh 7d)──▶ FastAPI
   /login /setup /accept-invite          SecurityHeaders middleware
   CSRF token (double-submit)            RateLimit middleware (strict on /auth/*)
                                         get_current_user dep ──▶ route (owner-filtered)
                                         require_admin dep   ──▶ admin route
```

Identity lives in the backend. Each existing router gains an auth dependency. Ownership
is enforced in-route: list endpoints filter by `owner_id` (admins bypass); mutations call
`require_owner_or_admin`. Setup-gate: while 0 users exist only `/auth/setup` succeeds;
after the first admin is created it returns 404.

## Components

Each module is small, single-purpose, < 500 lines.

### Backend — new
| Module | Responsibility | Depends on |
|--------|----------------|-----------|
| `app/security/passwords.py` | Argon2id `hash_password` / `verify_password` | argon2-cffi |
| `app/security/tokens.py` | JWT encode/decode; access 15m, refresh 7d, `jti` claim | pyjwt, config |
| `app/security/csrf.py` | issue CSRF cookie; verify `X-CSRF-Token` on unsafe methods | secrets |
| `app/security/deps.py` | `get_current_user`, `require_admin`, `require_owner_or_admin` | tokens, db |
| `app/security/setup_gate.py` | `users_exist(session)` for setup/lockout logic | db |
| `app/middleware/security_headers.py` | CSP, HSTS, X-Frame-Options=DENY, nosniff, Referrer/Permissions-Policy | — |
| `app/middleware/rate_limit.py` | in-memory sliding-window; strict `/auth/*`, lenient default | config |
| `app/routers/auth.py` | `/auth/setup`, `/login`, `/logout`, `/refresh`, `/me`, `/accept-invite` | above |
| `app/routers/users.py` | admin: list/create/disable users, change role, generate invite | deps |

### Backend — modified
- `app/models.py` — add `User`, `Invite`, `RefreshToken`; add `owner_id` to `Instance` and
  `ServiceTemplate` (template `owner_id` nullable; null = shared/admin-authored).
- `app/database.py` `_run_migrations` — add `owner_id` columns; backfill existing
  instances/templates to the first admin on setup.
- `app/config.py` — `JWT_SECRET` (fail-fast if unset in secure mode), `ACCESS_TTL=900`,
  `REFRESH_TTL=604800`, `COOKIE_SECURE=true`, `RATE_LIMIT_AUTH`, `RATE_LIMIT_DEFAULT`.
- `app/main.py` — remove `.admin_token` block; add SecurityHeaders + RateLimit middleware;
  tighten CORS (explicit method/header allowlist, keep credentials); register `auth` +
  `users` routers; add `get_current_user` dep to templates/instances/registry/images and
  inline `/api/system/*` (admin-gate metrics/gpu/purge).
- `app/schemas.py` — login, setup, invite, user CRUD request/response models.

### Data model
```
User:         id, username(uniq), email, password_hash, role(admin|user),
              is_active, must_change_pw, created_at, last_login
Invite:       id, token_hash, email, role, created_by, expires_at, used_at(null=unused)
RefreshToken: jti, user_id, expires_at, revoked, user_agent, created_at
Instance:     + owner_id FK → User.id
ServiceTemplate: + owner_id FK → User.id (nullable = shared)
```

### Frontend — React 19 + React Query (adopt installed `react-router`)
- `src/api/client.ts` — `credentials: "include"`; read CSRF cookie → `X-CSRF-Token` on
  POST/PUT/PATCH/DELETE; on 401 → redirect `/login`.
- `src/auth/AuthContext.tsx` + `useAuth` — `/auth/me` on load; exposes user/role/login/logout.
- `src/auth/ProtectedRoute.tsx` — gate app shell; redirect `/login` or `/setup`.
- New pages: `LoginPage`, `SetupWizard` (zxcvbn strength meter), `AcceptInvitePage`.
- Admin **Users** sub-tab under System: list/create/disable users, invite links, role change.
- Wrap `App.tsx` tab UI in the protected router shell. Build UI with `frontend-design`
  skill; match existing semantic-token theme.

## AuthZ pattern (reused across routers)
```python
# list
stmt = select(Instance)
if user.role != "admin":
    stmt = stmt.where(Instance.owner_id == user.id)
# mutate
require_owner_or_admin(instance.owner_id, user)
```

## Security hardening (industry standard)
- **SQLi** — SQLModel/SQLAlchemy parameterized (safe). Audit the raw f-string in
  `_run_migrations`; confirm only static table/column literals reach it. No user input.
- **XSS** — React auto-escapes; CSP blocks inline/eval. Audit `dangerouslySetInnerHTML`
  (server-static unavailable-HTML is fine).
- **Session hijack** — httpOnly+Secure+SameSite=Strict cookies; refresh rotation +
  revoke-on-logout via `jti`/`RefreshToken`; short access TTL.
- **CSRF** — double-submit token (cookie auth requires it).
- **CORS** — explicit method/header allowlist; keep credentials.
- **Headers** — CSP, HSTS, X-Frame-Options=DENY, X-Content-Type-Options=nosniff,
  Referrer-Policy, Permissions-Policy.
- **Passwords** — Argon2id; zxcvbn strength gate on set/change.
- **Rate limiting** — strict sliding-window on `/auth/login` + `/auth/accept-invite`;
  lenient global default.
- **Secrets** — `JWT_SECRET` from env, fail-fast if missing in secure mode; retire
  `.admin_token` logging.

## Error handling
- Auth failures → 401 with generic `detail` (no user-enumeration: same message for
  bad username vs bad password).
- Authz failures → 403.
- Rate-limit trip → 429 with `Retry-After`.
- Expired access token → 401; frontend silently calls `/auth/refresh` then retries once,
  else redirects `/login`.
- Setup attempted after first admin → 404 (route disappears).

## Testing
- pytest: Argon2 hash/verify; JWT encode/decode/expiry/revoke; CSRF accept+reject;
  setup-gate (0 users→setup only, then locked); login success/fail + rate-limit trip;
  invite single-use; ownership filter (user sees own only, admin sees all); every
  protected route → 401 unauthenticated. Keep 44 existing tests green (authed-client
  fixture in `conftest.py`).
- Manual e2e: fresh DB → `/setup` → existing instances owned by admin → login → create
  instance → invite user 2 → user 2 sees none of admin's → admin sees all → logout
  revokes refresh.
- `curl -I` protected route → CSP/HSTS/X-Frame-Options present; cookies HttpOnly+Secure+SameSite.

## Critical files to reuse
- `backend/app/main.py:198-211` — middleware + router registration site.
- `backend/app/models.py` — `_uuid`, `_now`, JSON-column patterns.
- `backend/app/database.py` `_run_migrations` — raw-SQL migration approach.
- `backend/app/routers/instances.py` — `Depends(get_session)` pattern to extend with auth dep.
- `backend/tests/conftest.py` — DI override; extend with authed-client fixture.
- `frontend/src/api/client.ts:13-24` — central `request()` wrapper (single CSRF/401 site).
- `frontend/src/hooks/use-instances.ts` — React Query hook pattern to mirror.
