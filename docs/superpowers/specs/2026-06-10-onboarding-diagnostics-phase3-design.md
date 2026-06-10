# Onboarding & Diagnostics — Phase 3 Design

Date: 2026-06-10
Status: Approved (user, 2026-06-10)
Scope: Phase 3 of 3. Phases 1 (security) + 2 (UI polish) merged.
Stack: FastAPI backend + React frontend (no FE unit runner; backend pytest).

## Goal

Make Styx Portal operable and self-explanatory: a beginner can tell at a glance whether
the system is healthy, get actionable errors during first-run setup, see progress when a
big image pulls, and follow docs split into quick-start vs production. Power users get deep
diagnostics with history.

## Decisions (user-approved)

- Full Phase 3: all five groups below.
- Diagnostics depth: **deep + history** — per-check status + latency + a status-over-time view.

## Current-state notes (verified)

- `metrics_store.py` already has a ring-buffer pattern (cpu/ram/timestamps, 24h @ 30s) and a
  background `_metrics_collection_loop` in `main.py`. Reuse the pattern for health history.
- **No SSE/WebSocket anywhere.** Pull progress therefore piggybacks on the EXISTING instance
  status polling (the launch UI already polls), not a new transport.
- docker-socket-proxy allows `PING`, `INFO`, `EVENTS`, `CONTAINERS`, `IMAGES`, `NETWORKS`,
  `VOLUMES`; denies `SYSTEM` (so `df` stays unavailable — disk via `shutil`). `client.ping()`,
  `client.version()`, `client.info()` work through the proxy.
- Instance pull happens in `_launch_instance_background` (instances.py): status flips
  `pulling`→`starting`→`running`. `docker.image_exists()` decides if a pull is needed.
- Setup gate: `GET /api/auth/setup-required` + `POST /api/auth/setup`; only usable while no
  users exist (`users_exist`).

## Group A — Diagnostics endpoint + history (backend)

Files: new `app/services/diagnostics.py`, new `app/services/health_store.py`, `app/main.py`
(endpoints + background sampler), `app/services/docker_manager.py` (add `ping`/`version` helpers).

- `run_diagnostics(session)` → runs each check, returns:
  ```json
  { "ok": true, "checked_at": "<iso>", "checks": [
    { "key": "docker", "ok": true, "latency_ms": 4, "detail": "Engine 29.5.2 via socket-proxy" },
    { "key": "database", "ok": true, "latency_ms": 1, "detail": "writable" },
    { "key": "traefik_routes", "ok": true, "latency_ms": 0, "detail": "writable, last write 12s ago" },
    { "key": "disk", "ok": true, "latency_ms": 0, "detail": "63% free (120/190 GB)" },
    { "key": "gpu", "ok": true, "latency_ms": 2, "detail": "nvidia detected" }
  ] }
  ```
  Checks (each timed, never raises — failures become `ok:false` + detail):
  - **docker:** `client.ping()` + `client.version()` through the configured socket (covers the
    socket-proxy path too). detail = engine version or the error.
  - **database:** execute a trivial write+rollback (or `SELECT 1`) on the session. detail =
    writable / error.
  - **traefik_routes:** `TRAEFIK_DYNAMIC_DIR` exists + writable; report age of `routes.yml`.
    Surfaces the non-root-volume-permission class of failure from Phase 1.
  - **disk:** `shutil.disk_usage("/")` → free %, warn (`ok:false`) under a threshold (e.g. <10%).
  - **gpu:** `detect_gpu()` — informational; `ok:true` always (absence isn't a failure), detail
    says detected type or "none".
  - Overall `ok` = all non-informational checks pass.
- `GET /api/system/diagnostics` (admin) → `run_diagnostics`.
- **History:** `health_store.py` ring buffer (status bitmap + per-check latency, maxlen ~2880).
  A background `_health_sample_loop` in `main.py` (every ~60s) runs the checks and records a
  sample. `GET /api/system/diagnostics/history?range=1h|6h|24h` (admin) → timestamps + per-check
  up/down series + latency series, for a small status-over-time view.
- Tests: each check returns ok/fail shape; disk threshold; overall-ok aggregation; history
  records + range slicing; admin gating (member → 403). Mock docker client (ping/version).

## Group B — Health page (frontend, admin)

Files: new `src/components/system/health-panel.tsx`, `src/api/client.ts` (+ types), settings
nav (add an admin-only "Health" entry).

- Admin-gated page: top banner (all-good green / degraded red), then a list of checks — each a
  row with status dot, key (friendly label), latency, detail string. Auto-refresh every ~30s
  (React Query `refetchInterval`) + a manual "Run checks" button.
- A compact status-over-time strip per check from the history endpoint (simple up/down bars;
  reuse the existing chart/sparkline approach in `lib/chart.ts` if it fits, else minimal bars).
- Friendly labels + remediation hints for failures (e.g. traefik_routes fail → "Routes volume
  not writable — see Production Checklist").

## Group C — Setup-wizard validation (backend + frontend)

Files: `app/routers/auth.py` (new pre-setup check endpoint), `src/pages/SetupWizard.tsx`.

- `GET /api/auth/setup-preflight` — available ONLY while `not users_exist` (404 once an admin
  exists, like setup). Returns a SAFE subset of diagnostics relevant to first-run: docker
  reachable (bool + detail), deploy_mode (`tunnel`/`direct`), domain set (bool), data dir
  writable. No secrets, no host internals beyond up/down + the configured DEPLOY_MODE/DOMAIN.
- SetupWizard renders a preflight panel above the create-admin form: green checks or actionable
  red items ("Docker not reachable — is the socket-proxy running?"). Non-blocking (admin can
  still proceed) but visible, so first-run failures surface in the UI, not just logs.
- Tests: preflight returns shape; 404 after a user exists; docker-unreachable path reports
  ok:false without raising.

## Group D — Docker pull progress (backend + frontend)

Files: `app/services/docker_manager.py` (streaming pull), `app/routers/instances.py` (capture
progress), `app/models.py` (transient progress field OR in-memory map), `src/components/instances/*`
(show progress on a pulling instance).

- Replace the blocking `images.pull(image)` in the launch path with a streaming pull:
  `client.api.pull(repo, tag, stream=True, decode=True)` — iterate layer events, compute an
  overall percent (downloaded/total across layers), and write it where the status poll can read
  it. Cheapest storage: an in-memory `dict[instance_id, {percent, status}]` in a small module
  (like metrics_store) updated from the background task; surfaced via the existing
  `GET /api/instances/{id}/status` (add `pull_percent`/`pull_detail` to its response) — NO new
  model column, NO new transport. The pull runs in `asyncio.to_thread` already.
- Frontend: where an instance shows `pulling`, render the percent + a thin progress bar (from
  the status poll the launch/detail UI already does). Falls back to indeterminate if percent
  unknown.
- Tests: the pull-progress store updates/reads; status endpoint includes pull fields while
  pulling and clears them after. Mock the pull event stream.

## Group E — Docs split

Files: `README.md` (slim to overview + links), new `docs/QUICKSTART.md`,
`docs/PRODUCTION.md`, `docs/GPU.md`, `docs/ADMIN.md`.

- **QUICKSTART.md** — 5-minute path: clone, `cp .env.example .env`, set DOMAIN + CF token (or
  direct mode), `docker compose up -d`, open, create admin. The happy path, tunnel mode default.
- **PRODUCTION.md** — checklist: direct-mode TLS (LE DNS-01, the env vars), backups (the
  `secrets.json` + `db-data` volume), the security posture summary (socket-proxy, confined
  containers, audit log at `/api/audit`, dashboard off), health monitoring (`/api/system/diagnostics`),
  the host-only gates from Phase 1 (capability tuning, GID setup), upgrade notes.
- **GPU.md** — driver/runtime prerequisites, `VIDEO_GID`/`RENDER_GID` (`getent group video render`),
  how to verify GPU in a container, troubleshooting.
- **ADMIN.md** — inviting users (the invite box, 72h expiry), roles + SSO providers (incl.
  `auto_promote_admins`), templates (incl. DinD is admin-only + needs limits), reading the audit
  log + Health page, quotas (`MAX_INSTANCES_PER_USER`).
- README keeps the architecture overview + a links section to the four docs; drop the stale
  "Authentik ForwardAuth" framing (native SSO now).

## Non-goals (Phase 3)

- SSE/WebSocket transport (pull progress reuses polling).
- Persisting health history to the DB (in-memory ring buffer like metrics_store is enough;
  resets on restart — acceptable, documented).
- Alerting/notifications on health degradation (future).
- Virtual scrolling, i18n, the deferred live idle-countdown from Phase 2.

## Testing

- Backend: pytest per Group A/C/D as listed (mock docker client + pull stream). Full suite +
  ruff must stay green (currently 267 passing).
- Frontend: `tsc --noEmit` + `vite build` + manual checks (no unit runner).
- Each group ships as its own commit(s).

## Risks

- **Diagnostic checks must never raise** — wrap each; a check failing is a result, not a 500.
- **Pull-percent accuracy** — docker layer events give per-layer progress; a rough overall % is
  fine (don't over-engineer exact bytes). Indeterminate fallback when totals unknown.
- **Preflight pre-auth exposure** — keep it to up/down + already-public config (DOMAIN,
  DEPLOY_MODE); gate to first-run-only; no host internals or secrets.
- **History is in-memory** — resets on restart; documented, acceptable for a single-host portal.
