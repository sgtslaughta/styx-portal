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

Diagrams are Excalidraw drawings rendered to SVG, one light and one dark variant each, in `docs/assets/diagrams/`. They are born from Mermaid, which stays the quickest way to draft one.

- **Sources:** `<page-slug>-<n>.mmd` (Mermaid) and `<page-slug>-<n>.excalidraw` (scene JSON, the editable master). The SVGs `<name>-light.svg` and `<name>-dark.svg` are generated; commit them.
- **New diagram:** write a fenced Mermaid block in the page, then run `scripts/diagrams/from-mermaid.sh`. It extracts each block to a `.mmd`, converts it with `@excalidraw/mermaid-to-excalidraw`, renders both SVGs and swaps the block for image links. Replace the `TODO alt` text with a short description. To redo one diagram from its `.mmd`, pass its name: `scripts/diagrams/from-mermaid.sh operate-webrtc-turn-1`. This overwrites its `.excalidraw`.
- **Hand edits:** open the `.excalidraw` file on excalidraw.com, edit, save it back, then run `scripts/diagrams/render.sh [name...]`. The `.mmd` is then only the first draft.
- **Links:** docs pages use two images, `![alt](../assets/diagrams/<name>-light.svg#only-light)` and the `-dark.svg#only-dark` twin. The README uses a `<picture>` element with a `prefers-color-scheme: dark` source.
- **Roles, not colours:** tag Mermaid nodes with `:::role` and end with the `classDef` lines. Roles: `ext` (browser, outside world), `core` (Styx services), `gate` (Traefik, tunnel, proxies), `run` (workloads, desktops, apps), `store` (databases, volumes, registries), `bad` (deny, error), `chk` (a check step, outlined only). Copy the fill and stroke values from an existing `.mmd`; the converter applies them, and the dark render pre-compensates Excalidraw's dark filter so they keep the brand look.
- **Shapes and size:** quote every label, use `subgraph` for trust zones and prefer `flowchart TD` for more than about six nodes.
- **Tooling:** Node and Chromium run only inside the Playwright Docker image, never on the host; the first run installs the pinned packages from `scripts/diagrams/package.json`.
