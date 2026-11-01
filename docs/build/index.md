# Build

Engineering documentation for Styx Portal contributors and anyone who wants to
understand how the pieces fit. The operator-facing guides live under Operate;
this section explains the code.

!!! note "What you will get"
    A mental model of the system (browser, Traefik, backend, runtimes,
    workstation agent), where each concern lives in the repo, and the rules for
    changing it (tests, commits, releases).

## Reading order

1. [Architecture](architecture.md): the big picture, request and auth flow, data model.
2. [Backend](backend.md): FastAPI layout, settings service, Docker vs Kubernetes runtimes, Traefik routing.
3. [Frontend](frontend.md): React app, API client, the second (shell) build, theming.
4. [Agent](agent.md): the workstation agent, gateway, engine, GNOME and labwc seats.
5. [Streaming](streaming.md): pixelflux and selkies pipeline, transports, the A/B latency harness.
6. [Security](security.md): threat model, auth, brute-force layers, secrets at rest.
7. [Testing](testing.md): pytest, vitest, Playwright e2e, CI.
8. [Releases](releases.md): semantic-release, images, agent versioning, CI/CD design.
9. [Contributing](contributing.md): dev setup, commit and PR rules.
10. [Upstream contributions](upstream.md): patches sent to selkies and pixelflux.
11. [Architecture decision records](../decisions/index.md): why the pipeline looks the way it does.

## Suggested nav order

For the nav owner (`zensical.toml`); paths are relative to `docs/`.

1. `build/index.md`
2. `build/architecture.md`
3. `build/backend.md`
4. `build/frontend.md`
5. `build/agent.md`
6. `build/streaming.md`
7. `build/security.md`
8. `build/testing.md`
9. `build/releases.md`
10. `build/contributing.md`
11. `build/upstream.md`
12. `decisions/index.md`

`docs/CICD.md` and `docs/AGENT_BUILD.md` are merged into
[Releases](releases.md) and [Agent](agent.md); their old pages can become stubs.

## Repository map

| Path | What lives there |
|------|------------------|
| `backend/` | FastAPI app (`app/`), pytest suite (`tests/`) |
| `frontend/` | React + Vite app; second build `shell.html` under `src/shell/` |
| `agent/` | Workstation agent, gateway, engine, seats, `enroll.sh`, tests |
| `e2e/` | Playwright full-stack suite and the stream A/B harness (`e2e/stream-ab/`) |
| `deploy/k8s/` | Kustomize manifests for Kubernetes |
| `traefik/` | Static config and the local `styxlocation` plugin |
| `templates/` | Seeded desktop templates; `templates/services/` holds proxy presets |
| `scripts/` | `build-docs.sh`, `build_agent_artifacts.sh`, `stamp-version.sh`, ... |
| `docs/decisions/` | ADRs |
| `docs/upstream/` | Patches and write-ups for selkies and pixelflux |
