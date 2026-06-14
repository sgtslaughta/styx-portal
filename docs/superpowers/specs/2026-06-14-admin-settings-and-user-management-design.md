# Admin-Exposed Server Settings + User Management — Design Spec

**Date:** 2026-06-14
**Status:** Approved (design), pending implementation plan
**Scope:** Expose safe server behavioral settings in the admin panel (editable at runtime, env-seeded), and close the user-management gaps (unlock, password reset, force-change, delete-if-empty, self change-password, password policy).

## Problem

All of `app/config.py` is **env-only and immutable at runtime** — there is no settings table, so an admin cannot tune brute-force thresholds, rate limits, timeouts, quotas, or password rules without editing `.env` and restarting the container. Separately, admin user management is missing standard actions: no manual unlock, no password reset, no force-password-change, no delete, and there is no self-service password-change endpoint at all (the `must_change_pw` flag exists but is unsatisfiable).

## Goals

1. A runtime-mutable settings store, seeded by env defaults, that admins edit from the panel and that applies **live** (no restart).
2. Secrets and infrastructure config stay env-only and are never exposed or editable via the UI/API.
3. Close the user-management gaps with audited, guarded admin actions plus a self password-change flow and an enforced password policy.

## Non-Goals

- Editing secrets/infra via UI (JWT_SECRET, DATABASE_URL, DOCKER_*, DEPLOY_MODE, paths, SELKIES_APP_URL, LAN/cert dirs) — remain env-only.
- 2FA/MFA, granular RBAC beyond admin/user, bulk invite, hard delete of users who still own resources.
- Per-template/per-workstation settings (already DB-mutable via existing APIs) — unchanged.

## Architecture — 5 Components

```
config.py (env defaults / seed)
        │  fallback when no override
        ▼
SystemSettings (DB KV: overrides only) ── SettingsService.get(key) ◄── all use-time reads
        ▲                                          │ on_change hooks
   PATCH /api/system-settings (admin)              ├─ Traefik knobs → route_writer rewrite
        ▲                                          └─ (rate-limit/lockout/etc. read live, no hook)
   system-settings-panel.tsx
```

### Component 1 — Runtime settings store

**Table** `system_settings` (`app/models.py`):
- `key: str = Field(primary_key=True)`
- `value: Any = Field(sa_column=Column(JSON))` — the override value
- `updated_at: datetime = Field(default_factory=_now)`
- `updated_by: str | None = None` — acting admin user id

Stores **only overrides**. A key with no row → the effective value is the `config.py` default.

**Service** `app/services/settings_store.py` — `SettingsService`:
- A module-level `SCHEMA: dict[str, SettingSpec]`. `SettingSpec` fields:
  `key, group, label, help, type ("int"|"bool"|"rate"), config_attr (name in Settings, or None for new keys), default (used when config_attr is None), constraints (min/max for int; regex `^\d+/\d+$` for rate), on_change (callable name or None)`.
- `get(key) -> value`: return the cached override if present, else the seed default
  (`getattr(_settings, spec.config_attr)` when `config_attr` set, else `spec.default`). Raises `KeyError` for keys not in SCHEMA.
- `effective() -> list[group dicts]`: for the UI — each key with `{key, group, label, help, type, value, default, constraints}`.
- `set(session, key, value, actor_id)`: validate against SCHEMA constraints (raise `ValueError` on violation) → upsert row → invalidate cache → run `on_change` if any.
- `reset(session, key, actor_id)`: delete the override row → invalidate cache → run `on_change`.
- In-memory cache: `dict[str, value]` loaded lazily from DB + seeds; a `reload(session)` repopulates; single-process so a simple dict + invalidate-on-write is sufficient (mirrors BanCache pattern). The service exposes a sync `get` backed by the cache; cache is warmed at startup (lifespan) and after each write.
- Module singleton `settings` (like `fail_tracker`/`ban_cache`).

**Registered keys (SCHEMA) — ONLY these are exposable:**

| Group | Key | type | constraints | config_attr |
|---|---|---|---|---|
| brute_force | LOCKOUT_THRESHOLD | int | 1–100 | LOCKOUT_THRESHOLD |
| brute_force | LOCKOUT_DURATION | int | 30–86400 | LOCKOUT_DURATION |
| brute_force | BAN_FAIL_THRESHOLD | int | 1–1000 | BAN_FAIL_THRESHOLD |
| brute_force | BAN_FAIL_WINDOW | int | 30–86400 | BAN_FAIL_WINDOW |
| brute_force | BAN_DURATION | int | 60–604800 | BAN_DURATION |
| rate_limits | RATE_LIMIT_AUTH | rate | `^\d+/\d+$` | RATE_LIMIT_AUTH |
| rate_limits | RATE_LIMIT_DEFAULT | rate | `^\d+/\d+$` | RATE_LIMIT_DEFAULT |
| rate_limits | RATE_LIMIT_INSTANCE_CREATE | rate | `^\d+/\d+$` | RATE_LIMIT_INSTANCE_CREATE |
| rate_limits | TRAEFIK_RATELIMIT_AVERAGE | int | 1–100000 | TRAEFIK_RATELIMIT_AVERAGE |
| rate_limits | TRAEFIK_RATELIMIT_BURST | int | 1–100000 | TRAEFIK_RATELIMIT_BURST |
| sessions | ACCESS_TTL | int | 60–86400 | ACCESS_TTL |
| sessions | REFRESH_TTL | int | 300–2592000 | REFRESH_TTL |
| timeouts | WORKSTATION_IDLE_TIMEOUT_S | int | 60–86400 | WORKSTATION_IDLE_TIMEOUT_S |
| timeouts | WORKSTATION_OFFLINE_AFTER_S | int | 30–3600 | WORKSTATION_OFFLINE_AFTER_S |
| quota | MAX_INSTANCES_PER_USER | int | 0–1000 | MAX_INSTANCES_PER_USER |
| password_policy | PASSWORD_MIN_LENGTH | int | 8–256 | None (default 12) |
| password_policy | PASSWORD_REQUIRE_UPPER | bool | — | None (default false) |
| password_policy | PASSWORD_REQUIRE_LOWER | bool | — | None (default false) |
| password_policy | PASSWORD_REQUIRE_DIGIT | bool | — | None (default false) |
| password_policy | PASSWORD_REQUIRE_SYMBOL | bool | — | None (default false) |

The 5 password-policy keys are also added to `config.py` (so env can seed them); `config_attr` then points at them. (Spec lists `None` to signal they are NEW; implementation adds the config fields and wires `config_attr`.)

### Component 2 — All-live read-point refactor

Replace use-time `_settings.X` reads with `settings.get("X")` so edits apply immediately:
- `app/routers/auth.py` login — `LOCKOUT_THRESHOLD`, `LOCKOUT_DURATION`, `BAN_DURATION`.
- `app/services/abuse.py` — `IpFailTracker` reads `BAN_FAIL_THRESHOLD`/`BAN_FAIL_WINDOW` at `record()` time (not at construction); `BanCache` TTL read at `is_banned()` time. (Refactor the singletons to read live rather than capture at import.)
- `app/security/tokens.py` — `ACCESS_TTL`/`REFRESH_TTL` read at token creation.
- `app/routers/instances.py` — `MAX_INSTANCES_PER_USER` at create.
- `app/middleware/rate_limit.py` `RateLimitMiddleware` — read `RATE_LIMIT_AUTH`/`RATE_LIMIT_DEFAULT` from the store per request; memoize the parsed `SlidingWindow` per spec string, rebuild when the spec changes.
- `app/services/route_writer.py` — read `TRAEFIK_RATELIMIT_*` from the store; the settings `on_change` for those two keys triggers `refresh_routes_from_db` so `routes.yml` is rewritten live.
- `app/services/session_monitor.py` / workstation monitor — read `WORKSTATION_IDLE_TIMEOUT_S` / `WORKSTATION_OFFLINE_AFTER_S` from the store at loop time.

Reads that must stay env-frozen (DB URL, network, secret) are untouched.

### Component 3 — Settings admin API + tab

**Router** `app/routers/system_settings.py` (mounted `/api/system-settings`, all `require_admin`, audited):
- `GET /` → `settings.effective()` grouped output.
- `PATCH /` → body `{ "<key>": <value>, ... }`; validate each against SCHEMA; apply via `settings.set`; audit `settings.update` with changed keys (values, no secrets); return updated effective values. Reject unknown keys with 400.
- `POST /{key}/reset` → `settings.reset`; audit `settings.reset`.

**Frontend** `frontend/src/components/system/system-settings-panel.tsx`:
- New nav entry under **Administration** group in `nav-config.tsx` (`adminOnly: true`), e.g. "Settings".
- Renders groups (Brute-force, Rate limits, Sessions, Timeouts, Quota, Password policy) as cards; number inputs / switches / rate-spec text inputs bound to effective values; per-group **Save** (PATCH changed keys) and per-field **Reset to default**; inline client validation mirroring constraints; `toast` on success/error; React Query invalidation. Add `api.getSystemSettings`, `api.updateSystemSettings`, `api.resetSystemSetting` to `api/client.ts`.

### Component 4 — User management actions

**Backend** `app/routers/users.py` (all `require_admin`, audited; guards below):
- `GET /api/users` — expand `UserOut` to add `last_login`, `locked_until`, `failed_count`. (Schema change in `app/schemas.py`.)
- `POST /api/users/{id}/unlock` — set `failed_count=0`, `locked_until=None`. Audit `user.unlock`.
- `POST /api/users/{id}/reset-password` — generate a strong temp password (≥ policy), set hash, `must_change_pw=true`, revoke all the user's refresh tokens; return the temp password ONCE in the response. Audit `user.reset_password` (no password in audit detail).
- `POST /api/users/{id}/force-password-change` — set `must_change_pw=true`. Audit `user.force_password_change`.
- `DELETE /api/users/{id}` — allowed only when the user owns 0 instances and 0 templates; else 409 with a message naming the blocker. Block deleting self and the last active admin. Hard-delete the user row and their refresh tokens + federated identities. Audit `user.delete`.
- Existing `disable` and `role` endpoints unchanged.

**Self password-change (gap fix)** `app/routers/auth.py`:
- `POST /api/auth/change-password` (`get_current_user`) — body `{old_password, new_password}`; verify old; enforce password policy on new; set hash; clear `must_change_pw`; rotate the session (issue fresh tokens, revoke the old refresh family). Audit `auth.password_change`.

**Frontend** `frontend/src/components/system/users-panel.tsx`:
- Show a **Locked** badge when `locked_until` is in the future; **Unlock** button.
- **Reset password** dialog → shows the one-time temp password with a copy button.
- **Force password change** action.
- `last_login` column.
- **Delete** action (guarded) via `ConfirmDialog`; surfaces the 409 reason.
- New **Change Password** screen/dialog for self-service (`api.changePassword`); the login flow redirects to it when `must_change_pw` is returned. Minimal page reusing `PasswordInput` + policy hints.

### Component 5 — Password policy

`app/security/passwords.py`:
- `validate_password(pw: str, policy: PasswordPolicy) -> None` — raises `ValueError` (mapped to 422 by callers) listing every unmet rule. `PasswordPolicy` is a small dataclass built from settings keys (`min_length`, `require_upper/lower/digit/symbol`).
- A helper `current_policy()` that reads the 5 settings keys via `settings.get`.

Enforced at: `POST /setup`, `POST /accept-invite`, `POST /auth/change-password`, and `POST /users/{id}/reset-password` (the generated temp password is built to satisfy the policy).

## Data / Config Changes

- `config.py`: add `PASSWORD_MIN_LENGTH: int = 12`, `PASSWORD_REQUIRE_UPPER/LOWER/DIGIT/SYMBOL: bool = False`.
- `models.py`: new `SystemSetting` table.
- `database.py`: `system_settings` table is created by `create_all` (new table — no column migration). No `User` schema change (lockout fields already exist).
- `schemas.py`: extend `UserOut`; add settings + password-change request/response schemas.
- `main.py`: register the `system_settings` router; warm the settings cache in lifespan.

## Error / Status Semantics

- 400 — unknown settings key / validation failure (with field + reason).
- 409 — delete user who still owns instances/templates (message names counts).
- 422 — password fails policy (lists unmet rules).
- 403 — non-admin on admin endpoints (existing `require_admin`); last-admin/self guards return 400/409 as today.
- All mutations audited; **no password or secret value is ever written to the audit log or returned except the one-time reset temp password in its own response body.**

## Testing Strategy

- **settings_store:** get returns override else seed default; set validates (min/max, rate regex) and rejects bad values + unknown keys; reset restores default; cache invalidation; on_change fires for Traefik keys.
- **live reads:** changing LOCKOUT_THRESHOLD mid-run changes lockout behavior without restart; rate-limit middleware picks up a new spec; Traefik knob change rewrites routes.yml (assert route_writer output reflects new value).
- **user actions:** unlock clears failed_count+locked_until; reset-password rotates refresh tokens + sets must_change_pw + temp pw satisfies policy; delete blocked when owning resources (409) and allowed when empty; self/last-admin guards.
- **self change-password:** wrong old → 401/422; weak new → 422; success clears must_change_pw + rotates tokens.
- **password policy:** validate_password matrix (length + each char class); enforcement at setup/accept-invite/change/reset.
- **authz:** every new endpoint rejects non-admin (settings, user actions) / unauthenticated (change-password).
- Use in-memory SQLite + the existing `client`/`admin_client` fixtures; monotonic/clock injection where windows matter.

## Security Notes

- The SCHEMA is an allowlist — only registered behavioral keys are reachable through the store or API; secrets/infra are structurally excluded (no row, no schema entry, no API path).
- PATCH validates every key server-side regardless of client validation; bounds prevent footguns (e.g., LOCKOUT_THRESHOLD=0).
- Reset-password returns the temp password once and never logs it; refresh-token revocation prevents the old session from surviving a reset.
- Delete is constrained to resource-empty users to avoid orphaned instances/templates (FK integrity).
- No new external dependencies; single-process cache (consistent with existing BanCache/health-store patterns).
