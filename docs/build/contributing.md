# Contributing

## Dev setup

Prerequisites: Python 3.12+, Node 22, Docker with Compose, Git.

=== "Backend"

    ```bash
    cd backend
    python3 -m venv .venv
    .venv/bin/pip install -e '.[dev]'
    .venv/bin/python -m pytest -q
    JWT_SECRET=dev-only-secret-at-least-32-characters COOKIE_SECURE=false DEV_CORS=true \
      .venv/bin/python -m uvicorn app.main:app --reload --port 8000
    ```

=== "Frontend"

    ```bash
    cd frontend
    npm ci
    npm run dev      # http://localhost:5173, /api proxied to :8000
    npm test
    npm run build    # the gate
    ```

=== "Full stack"

    ```bash
    cp .env.example .env     # set DOMAIN, secrets
    docker compose up -d     # profiles: tunnel (cloudflared) or direct (Let's Encrypt)
    ```

Release tooling (`commitlint`, `semantic-release`) installs from the repo root:
`npm ci`.

## Commit rules

* Conventional Commits with a **lowercase subject**: `feat(agent): offer av1 on nvenc hosts`.
* Types: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`, `ci`, `perf`, `build`. `feat` bumps minor, `fix` patch, `!` or `BREAKING CHANGE:` major.
* Scope is optional but useful: `agent`, `backend`, `frontend`, `docs`, `ci`, `k8s`.
* `commitlint` runs on every PR commit; check locally with `npx commitlint --from origin/main --verbose`.

## Pull requests

1. Branch from `main` (`feat/...`, `fix/...`, `docs/...`).
2. Keep a PR to one concern; add or update tests with the change.
3. Run the checks for what you touched (see [Testing](testing.md)): ruff and pytest for backend, `npm run build` and `npm test` for frontend, the agent tests for `agent/`.
4. If you change `agent/**` behaviour, bump `AGENT_VERSION`; if you add an agent module, add it to `AGENT_UPDATE_FILES` and `enroll.sh`.
5. Open the PR against `main`. CI must be green; `main` requires PRs and cannot be pushed to directly.
6. Docs-only changes to `docs/` publish on merge via Pages.

## Code guidelines

* **Files under 500 lines.** Split by responsibility before a file grows past that (several routers already have a matching `services/` module).
* Keep decisions in code comments short; use a `ponytail:` comment for a deliberate shortcut and say when to drop it.
* Prefer pure functions that take their inputs (route builders, engine command builders) so they are testable without Docker or a desktop.
* Never add third-party apt sources or toolchains for workstations: build on the server and ship artifacts ([Agent](agent.md#seats)).
* Secrets never go in logs, argv, commits or docs. Docs use demo values only (`styx.example.com`, `alice`, `10.0.0.x`).

## Decisions

Significant changes to CI/CD or architecture get a short ADR in
[`docs/decisions/`](../decisions/index.md): context, decision, consequences.

## Diagram style

Diagrams are Mermaid fences (` ```mermaid `), rendered by Zensical on the site and natively by GitHub in the README. They share one look:

- **Header:** every flowchart starts with the same front-matter block (`themeVariables.fontSize: 15px`, `flowchart.curve: basis`, spacing and padding). Copy it from any existing diagram.
- **Roles, not colours:** end the diagram with `classDef` lines for the roles you use and tag nodes with `:::role`. Roles: `ext` (browser, outside world), `core` (Styx services), `gate` (Traefik, tunnel, proxies), `run` (workloads, desktops, apps), `store` (databases, volumes, registries), `bad` (deny, error), `chk` (a check step, outlined only). Fill and stroke values are the same in every diagram; copy them from an existing one.
- **Shapes:** rounded nodes `("text")` by default, `[("text")]` for stores, `{{"text"}}` for decisions (hexagons stay short in vertical charts). Quote every label.
- **Zones:** use `subgraph` for trust zones (edge, portal, cluster, workstation).
- **Size:** prefer `flowchart TD` for more than about six nodes; wide `LR` charts shrink to unreadable on a laptop.
- **Theming:** `docs/stylesheets/extra.css` maps the `--md-mermaid-*` variables to the Styx palette for the light and dark schemes (node, edge, label and sequence colours). `classDef` cannot use `var()`, so role fills are static mid-tones that stay readable under both label colours.
- **No icons:** Font Awesome icons (`fa:`) are not loaded by the site; skip them.
- **Check:** run `scripts/build-docs.sh`-style build and view the page in both schemes; the site loads Mermaid 11 from unpkg at view time.
