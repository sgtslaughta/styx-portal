# Backend

FastAPI + SQLModel on SQLite (async via `aiosqlite`). Python 3.12+.

## Layout

```
backend/app/
  main.py            app, lifespan, middleware, router registration
  config.py          Pydantic Settings (env-driven, boot-time defaults)
  database.py        engine, session factory, init_db, template seeding
  models.py          SQLModel tables
  schemas.py, schemas_services.py   request/response models
  middleware/        rate_limit.py, security_headers.py
  routers/           HTTP surface, one file per resource
  security/          cookies, csrf, tokens, deps, passwords, crypto, same_origin, ...
  services/          business logic, runtimes, background loops
```

### Routers

| Router | Prefix | Purpose |
|--------|--------|---------|
| `auth`, `matrix`, `oauth` | `/api/auth` | Login, refresh, setup, matrix-card 2FA, SSO callbacks, `ban-check` |
| `users`, `groups`, `profiles` | `/api/users`, `/api/groups`, `/api/profiles` | User admin, membership, per-user preferences |
| `templates`, `instances`, `instance_thumbs`, `images`, `registry` | `/api/...` | Desktop lifecycle and image management |
| `workstations`, `enroll`, `agent` | `/api/workstations`, `/api/enroll`, `/api/agent` | Admin CRUD, public enrollment and artifacts, agent heartbeat |
| `services`, `service_mounts`, `service_icons`, `services_auth` | `/api/services`, `/internal`, `/_styx` | Proxied services, managed mounts, forwardAuth, cookie-root enter/exit |
| `instance_auth` | `/internal/instances` | forwardAuth for `/i/` routes |
| `system_settings`, `audit`, `oauth_admin` | `/api/...` | Admin settings, audit log, SSO provider admin |

`/internal/*` is never routed by Traefik to the public; only Traefik's
forwardAuth addresses (`BACKEND_INTERNAL_URL`) reach it.

### Services (selection)

| Module | Role |
|--------|------|
| `docker_manager.py`, `docker_files.py`, `docker_args.py`, `gpu_access.py` | Docker API wrapper, file read/write and probe containers, GPU device passthrough |
| `k8s_runtime.py`, `k8s_instances.py`, `k8s_instance_objects.py`, `k8s_api.py`, `k8s_prepull.py` | Kubernetes runtime (same method names as `DockerManager`) |
| `route_writer.py`, `k8s_routes.py`, `service_routes.py`, `traefik_labels.py` | Traefik dynamic config and its k8s translation |
| `session_monitor.py`, `background_loops.py` | Idle detection and the periodic tasks started in `lifespan` |
| `settings_store.py` | Runtime settings service |
| `workstations.py`, `ws_settings.py`, `ws_icon.py`, `ws_thumb.py`, `artifacts.py` | Workstation helpers, stream-settings resolver, agent update file list, artifact cache |
| `abuse.py`, `login_flow.py`, `matrix_card.py`, `federation.py`, `token_denylist.py` | Brute-force layers, login steps, 2FA card, SSO |
| `mount_edit.py`, `mount_jobs.py`, `service_health.py`, `service_favicon.py` | Managed mounts, health loop, favicons |
| `diagnostics.py`, `health_store.py`, `metrics_store.py` | Health page data |

## Startup (lifespan)

`main.py::lifespan` fails fast if `JWT_SECRET` is unusable, then: snapshots its
own network subnets (trusted-proxy detection), `init_db()`, announces the
first-run setup code when no user exists, marks interrupted mount jobs failed,
loads settings overrides, removes leftover probe containers (Docker only),
reconciles instance states with the runtime, writes initial Traefik routes, and
starts the background loops.

| Loop | Purpose |
|------|---------|
| session monitor | idle warning/stop for instances |
| metrics, health sample | Health page series |
| screenshot capture, service thumbnails | dashboard previews |
| service health | HTTP or docker-state probes for proxied services |
| k8s pre-pull | only when `ROUTE_BACKEND=k8s` |

## Settings service

Two layers:

1. **`config.py` `Settings`**: env-driven, read at boot (secrets, domain, paths,
   `ROUTE_BACKEND`, `DEPLOY_MODE`, ...). Changing these needs a restart.
2. **`services/settings_store.py` `SettingsService`**: an allowlist
   (`SCHEMA`, a list of `SettingSpec`) of admin-tunable values. Each spec has a
   key, group, label, help text, type (`int`/`bool`/`rate`), bounds and the
   `config_attr` it seeds from. Overrides live in the `system_settings` table and
   are cached in memory; they apply live with no restart. Keys in
   `_TRAEFIK_KEYS` (proxy rate limit) also trigger a route refresh.

Read a value with `settings.get("KEY")` at the point of use, never cache it at
import time.

### Add a setting

1. Add a `_spec(...)` row to `_SPECS` in `settings_store.py` (pick an existing
   `group` or add a label in `_GROUP_LABELS`).
2. Seed it: set `config_attr` to the matching `Settings` field (add the field to
   `config.py` if new) or give a `default`.
3. Use `settings.get("KEY")` where the value is consumed.
4. Add a test in `backend/tests/` (see `test_settings_store*` / `test_system_settings*`).
5. The frontend settings tab is schema-driven; check it renders the new row.
6. Document it in the Operate settings reference.

## Add a router

1. Create `routers/<name>.py` with `router = APIRouter()`.
2. Auth: `Depends(get_current_user)` or `Depends(require_admin)` from `security/deps.py`. Writes are CSRF-checked automatically for cookie-authenticated requests.
3. Register it in `main.py` with `app.include_router(<mod>.router, prefix="/api/<name>", tags=["<name>"])`.
4. Public or agent-facing paths that cannot carry a CSRF cookie must be added to `_CSRF_EXEMPT` / `_CSRF_EXEMPT_PREFIXES` deliberately (today: login, setup, `/api/enroll/`, `/api/agent/`).
5. Add request/response models in `schemas.py`; add tests (below).

!!! tip "Keep files small"
    The repo guideline is under 500 lines per file. Split a router into
    `<name>.py` plus a `services/<name>.py` module when it grows.

## Docker vs Kubernetes runtime

`services/k8s_runtime.py::instance_runtime()` picks the implementation from
`ROUTE_BACKEND`. Routers call methods such as start/stop/logs on whatever it
returns. Rules:

* New runtime methods go on **both** `DockerManager` and `K8sInstanceRuntime`, or raise `K8sUnsupported`.
* `ensure_instance_supported(template)` refuses templates the cluster cannot run (privileged, DinD, unsafe capabilities).
* Docker-only template fields are hidden in the UI on Kubernetes.

## Traefik routing (`route_writer.py`)

`build_routes_config(instances, domain, deploy_mode, workstations, services, k8s)`
is a **pure function** returning the Traefik dynamic config dict:

* static routers: `frontend` (priority 1), `api` (100), `instances_fallback` (`/i/`, 10) with the unavailable/error middlewares;
* middlewares `ip-ban-gate` (forwardAuth to `/api/auth/ban-check`) and `styx-ratelimit`;
* one router per running instance, per online workstation (forwardAuth to `/internal/workstations/{id}/auth-check`) and per proxied service;
* transport per `DEPLOY_MODE`: `tunnel` uses `web`+`websecure` entrypoints, `direct` uses `websecure` with the `letsencrypt` resolver and a wildcard cert.

`write_routes()` serializes under a lock and writes the YAML file (or, on k8s,
applies and prunes objects). `refresh_routes_from_db()` rebuilds from the DB;
call it after anything that changes what is routable.

## Session monitor

`SessionMonitor.check_instance` compares `last_activity` against the instance's
`session_config` (`idle_timeout`, `grace_period`, `never_timeout`) and returns
actions (warn, stop). Activity comes from the browser heartbeat and desktop
signals. Workstation idle is enforced separately by the agent gateway; see
[Agent](agent.md).

## Testing conventions

* In-memory SQLite, mocked Docker (`get_docker_manager` dependency override) and mocked k8s client.
* `tests/conftest.py` sets env (`JWT_SECRET`, `COOKIE_SECURE=false`, high rate limits) **before** importing `app`, overrides `get_session`, and resets abuse/settings state per test.
* `pytest` runs in `asyncio_mode = "auto"`; write `async def test_...` directly.
* Lint: `ruff` (line length 100) is blocking; `mypy` is a non-blocking baseline.

See [Testing](testing.md) for commands.
