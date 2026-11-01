# Testing

| Suite | Tool | Where | Blocking in CI |
|-------|------|-------|----------------|
| Backend | pytest (asyncio auto mode) | `backend/tests/` | yes |
| Frontend | vitest + Testing Library | `frontend/src/**/__tests__`, `*.test.ts(x)` | yes |
| Frontend types | `npm run build` (`tsc -b`) | `frontend/` | yes |
| Traefik plugin | `go test` | `traefik/plugins-local/src/github.com/styx-portal/styxlocation` | yes |
| Agent | pytest | `agent/tests/` | not in CI |
| Full stack | Playwright | `e2e/` | not in CI (run locally) |
| Stream quality | A/B harness | `e2e/stream-ab/` | no (needs real hardware) |

## Backend (pytest)

```bash
cd backend
.venv/bin/python -m pytest -q            # all
.venv/bin/python -m pytest tests/test_route_writer.py -v
.venv/bin/python -m ruff check app tests # lint, blocking
.venv/bin/python -m mypy                 # non-blocking baseline
.venv/bin/python -m bandit -c pyproject.toml -r app -ll -ii
```

Conventions:

* In-memory SQLite engine per test (`session` fixture); the FastAPI `get_session` dependency is overridden.
* Docker is always mocked (`get_docker_manager` override, or patching `docker.DockerClient.from_env`); k8s tests use a fake client.
* `conftest.py` sets `JWT_SECRET`, `COOKIE_SECURE=false`, `DEV_CORS=true` and generous rate limits **before** importing `app`, and resets abuse trackers and the settings cache between tests (autouse fixtures).
* Prefer testing pure builders (`build_routes_config`, `build_objects`, `resolve_stream_settings`) directly; they are pure on purpose.
* No sleeping on real time: loops are tested through single-pass functions (`_monitor_tick`, `_run_monitor_pass`).

## Frontend (vitest)

```bash
cd frontend
npm test            # vitest run (jsdom)
npm run test:watch
npm run build       # the gate: tsc -b + both vite builds
```

`src/test/setup.ts` loads jest-dom matchers, polyfills `ResizeObserver` (Radix)
and cleans up after each test. Test hooks and components with TanStack Query by
wrapping in a fresh `QueryClientProvider`.

## Agent (pytest)

The agent runs on a workstation, not in the backend venv, so its modules
`importorskip` heavy dependencies (aiohttp, dbus) and tests add `agent/` to
`sys.path` themselves. Most logic is pure functions (config builders,
`restart_plan`, `decide` for refit, `hw_encoders`) so tests need no desktop.

```bash
cd agent && ../backend/.venv/bin/python -m pytest tests -q
```

`aiohttp` comes from the backend `dev` extra, so the backend venv runs the gateway tests; D-Bus tests skip when `dbus` is not importable.

`test_packaging.py` checks that every locally imported agent module is served for self-update and that `enroll --upgrade` is atomic and self-restoring.

## End-to-end (Playwright)

`e2e/run.sh` builds and starts an isolated compose project (`styx-e2e`) with real
Sonarr and Jellyfin behind Traefik, a docker shim, and the backend, publishing
only `127.0.0.1:18080`. It then runs the Playwright suite (shell, cookie-root,
proxied services, screenshots) and tears everything down.

```bash
e2e/run.sh                    # whole suite
e2e/run.sh -g "cookie-root"   # filter by test name
KEEP=1 e2e/run.sh             # leave the stack running for debugging
```

On failure, stack logs are saved to `e2e/test-results/stack.log`.

!!! warning
    The e2e stack builds images and needs Docker; do not run it on a workstation
    you cannot afford to load.

## Stream harness

See [Streaming](streaming.md#latency-and-ab-harness-e2estream-ab). Its pure
parts (`latstats`, `netem`, `probes`, `suite_latency`) have unit tests:
`cd e2e/stream-ab && python3 -m pytest -q`.

## CI

Both pipelines run the same stages; see [Releases](releases.md#ci-stage-graph).

| Stage | GitHub Actions (`.github/workflows/ci.yml`) | GitLab (`.gitlab-ci.yml`) |
|-------|-----------|--------|
| Quality | `commitlint`, `quality` (ruff, mypy, `npm run build`) | `commitlint`, `ruff`, `mypy`, `frontend-build` |
| Test | `test` (pytest, vitest), `plugin-test` | `pytest`, `vitest`, `plugin-test` |
| Security | `security` (bandit, Trivy fs) | `bandit`, `trivy-fs` |

**Run before every commit:** the checks for the area you touched, matching the
blocking CI jobs above.
