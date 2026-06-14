# Brute-Force Protection — Design Spec

**Date:** 2026-06-13
**Status:** Approved (design), pending implementation plan
**Scope:** Layered login brute-force / abuse protection for the Styx Portal login flow.

## Problem

The portal has IP-based login rate limiting (`5/60` per IP on `POST /api/auth/login`,
`/accept-invite`, `/setup`; `120/60` default) via an in-memory sliding window
(`backend/app/middleware/rate_limit.py`). Gaps:

- **In-memory only** — counters reset on backend restart; no durable protection.
- **No per-username lockout** — one IP can still try `5/min` (7200/day) against a
  single account; distributed IPs spread guesses below the per-IP threshold.
- **No hard ban** — repeat offenders are never blocked at the proxy; every request
  still reaches the app.

## Non-Goals

- Host-level `fail2ban` / OS firewall banning (rejected: ties to deploy host; we are
  fully containerized behind Traefik).
- Traefik fail2ban/denyip **plugin** (rejected: needs `experimental.plugins` +
  boot-time fetch from the plugin registry — fragile for self-hosted/offline).
- CAPTCHA, MFA (out of scope for this pass).

## Architecture — Four Layers

```
req ──> Traefik
         ├─ L1 rateLimit (flood)         ──> 429
         ├─ L3 ip-ban-gate forwardAuth   ──> backend /api/auth/ban-check ──> 403 if banned
         └─> backend
              ├─ L0 in-mem 5/60 IP window ──> 429   (existing, unchanged)
              └─ POST /login ──> L2 lockout + L3 abuse detector
```

### L1 — Traefik `rateLimit` middleware (proxy, coarse)

- Native Traefik v3 `rateLimit` middleware, applied to the `frontend` and `api`
  routers (and their `-lan` variants).
- Config: `average=100`, `burst=50`, per source IP. Traefik's default IP strategy;
  ensure it reads the real client IP (depth/`X-Forwarded-For` consistent with the
  app's `client_ip_from_headers`).
- Emitted by `backend/app/services/route_writer.py` into the dynamic config
  `middlewares` dict; attached to the relevant routers' `middlewares` lists.
- Purpose: cheap flood wall across all routes, independent of the app.

### L2 — App credential lockout (per-username)

- `User` model (`backend/app/models.py`) gains two columns:
  - `failed_count: int = 0`
  - `locked_until: datetime | None = None`
- `POST /api/auth/login` logic (`backend/app/routers/auth.py`):
  1. If `user.locked_until` is set and `> now()` → return **423 Locked** with a
     `Retry-After` header; do **not** check the password.
  2. On invalid password → `failed_count += 1`; if `failed_count >= 10` →
     `locked_until = now() + 15min`, `failed_count = 0`. Persist.
  3. On successful auth → `failed_count = 0`, `locked_until = None`. Persist.
- Keyed by **username** → catches slow distributed-IP guessing the per-IP window
  misses. Existing in-memory `5/60` IP window (L0) stays as the fast first wall.
- Username enumeration: keep the response/timing for "locked" indistinguishable
  where practical — return the same generic error body the existing invalid-login
  path uses (lockout is signalled by status 423 + Retry-After, not a leakier body).
  For an unknown username, do not create state; behave as a normal failed login.
- Threshold/lockout values are config-driven (see Config).

### L3 — Traefik IP denylist via forwardAuth ban-gate (proxy)

- New table `banned_ip`:
  - `ip: str` (primary lookup key, indexed/unique)
  - `reason: str`
  - `banned_at: datetime`
  - `expires_at: datetime`
- **Abuse detector** (in the auth flow): track failed logins per IP in a short
  in-memory sliding window. When an IP reaches **20 failed logins within 10 min**
  → insert/refresh a `banned_ip` row with `expires_at = now() + 1h`. (Also bannable
  on the same condition from `/accept-invite` / `/setup` failures.)
- New endpoint `GET /api/auth/ban-check`:
  - Resolves client IP via `client_ip_from_headers`.
  - Returns **403** if the IP has an unexpired ban, else **200** (empty body).
  - Backed by an **in-memory ban-set cache** refreshed from `banned_ip` every ~30s
    (and on write) so the per-request path is a set lookup, not a DB query.
- `route_writer.py` defines a global `ip-ban-gate` forwardAuth middleware
  (`address: http://backend:8000/api/auth/ban-check`) and prepends it to the
  `frontend`, `api`, and `-lan` routers' middleware lists → banned IPs are blocked
  at the proxy, before reaching the app, across all routes.
  - Mirrors the existing `ws-forward-auth` pattern already in `route_writer.py`.
- Expired bans are lazily ignored by the cache (filter `expires_at > now`) and may
  be pruned by a periodic cleanup (reuse existing background-loop infra if cheap;
  otherwise prune opportunistically on cache refresh).

### L4 — Persistence model

- The transient `5/60` sliding window (L0) stays **in-memory** — no write-per-request
  amplification on the hot path; it self-heals within 60s after a restart.
- The **durable** protections live in SQLite and survive restart:
  - L2: `User.failed_count`, `User.locked_until`.
  - L3: `banned_ip` rows.
- This satisfies "persist rate-limit state" by persisting the *consequential* state
  (lockouts + bans) rather than every request timestamp.

## Config (`backend/app/config.py`)

New env-driven settings (with defaults):

| Setting | Default | Meaning |
|---|---|---|
| `LOCKOUT_THRESHOLD` | `10` | failed logins per username before lock |
| `LOCKOUT_DURATION` | `900` (s) | lock duration (15 min) |
| `BAN_FAIL_THRESHOLD` | `20` | failed logins per IP in window before ban |
| `BAN_FAIL_WINDOW` | `600` (s) | abuse-detector window (10 min) |
| `BAN_DURATION` | `3600` (s) | IP ban duration (1 h) |
| `BAN_CACHE_TTL` | `30` (s) | ban-set cache refresh interval |
| `TRAEFIK_RATELIMIT_AVERAGE` | `100` | L1 avg req/s per IP |
| `TRAEFIK_RATELIMIT_BURST` | `50` | L1 burst per IP |

Existing `RATE_LIMIT_AUTH` / `RATE_LIMIT_DEFAULT` unchanged.

## Files Touched

- `backend/app/models.py` — `User.failed_count`, `User.locked_until`; `BannedIP` model.
- `backend/app/config.py` — new settings above.
- `backend/app/routers/auth.py` — lockout logic, abuse detector, `GET /ban-check`.
- `backend/app/middleware/rate_limit.py` — (optional) shared per-IP fail-window
  helper for the abuse detector, or a new small module `services/abuse.py`.
- `backend/app/services/route_writer.py` — L1 `rateLimit` + L3 `ip-ban-gate`
  forwardAuth middlewares; attach to `frontend`/`api`/`-lan` routers.
- `backend/app/database.py` — migration/column add for the new `User` fields +
  `banned_ip` table (follow existing schema-creation approach).
- `frontend/src/lib/auth-errors.ts` — friendly messages for **423 Locked** and
  for the **403** ban (e.g. "Account temporarily locked" / "Access temporarily
  blocked").
- Tests: `backend/tests/test_rate_limit.py` (extend), new tests for lockout,
  abuse-detector → ban, `/ban-check`, and route_writer middleware emission.

## Error / Status Semantics

- **429** — rate limit (L0 app window or L1 Traefik). Existing behavior + new L1.
- **423 Locked** — per-username lockout (L2). New. `Retry-After` set.
- **403** — IP banned at proxy (L3 ban-gate). New. Generic body.
- Failed password (not yet locked/banned) — existing generic invalid-credentials
  response, unchanged.

## Testing Strategy

- Unit: lockout state machine (increment, lock at threshold, 423 while locked,
  reset on success); abuse detector (ban inserted at 20/10min, not before);
  ban-check (403 for active ban, 200 for expired/absent); ban-set cache refresh.
- route_writer: assert `rateLimit` and `ip-ban-gate` middlewares emitted and
  attached to `frontend`/`api`/`-lan` routers; forwardAuth address correct.
- Use in-memory SQLite + monotonic-clock injection (matches existing
  `SlidingWindow.allow(now=...)` test pattern) so windows/expiry are deterministic.

## Security Notes

- `ban-check` trusts proxy headers — acceptable because the backend is only
  reachable via Traefik (same assumption as existing `client_ip_from_headers`).
- Shared-NAT false positives: 20/10min threshold + 1h (not permanent) ban limits
  collateral for office/CGNAT egress IPs. Admin override (manual unban) can be a
  follow-up; not in this pass.
- No new external dependencies; no elevated container capabilities; no host changes.
