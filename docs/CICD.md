# CI/CD Architecture

Styx Portal runs one logical pipeline on two hosts: **GitHub Actions** (canonical)
and **GitLab CI** (push-mirror). This page documents the stage graph and the
reasoning behind every non-obvious choice. It is the single source of truth — if
a workflow file and this page disagree, the workflow is the bug.

## Stage graph

| Stage | Trigger | Tools | Gate |
|-------|---------|-------|------|
| Quality | push, PR/MR | ruff, mypy, frontend `tsc -b` | ruff/tsc block; **mypy non-blocking** |
| Test | push, PR/MR | pytest, vitest | block |
| Security | push, PR/MR | bandit, Trivy fs (vuln+secret) | fail HIGH/CRITICAL |
| Release | push default branch | semantic-release | block |
| Build | release version / tag `v*` | buildx → 3 images → GHCR + GitLab registry | block (desktop isolated) |
| Scan | post-build | Trivy image ×3 | fail HIGH/CRITICAL |
| Docs | push default branch | `scripts/build-docs.sh` → Pages | block |

## Why parity, and how it's maintained

GitHub is canonical; GitLab is a push-mirror so the project stays reachable on
both. Rather than a cross-platform meta-CI tool (extra dependency, lowest-common
-denominator features), each host uses **native idioms**: GitHub composite actions
(`.github/actions/setup-backend`, `setup-node`), GitLab YAML anchors + `extends`.
Parity is a property of the **stage graph and gates**, enforced by this document
and code review — not by shared YAML. The tradeoff is occasional manual sync; the
benefit is each pipeline uses its platform's best features (GH Pages OIDC deploy,
GitLab dotenv artifacts).

## Triggers: why tags build images but branches deploy docs

Docs are **idempotent and cheap** — redeploying on every default-branch push keeps
the site current. Images are **immutable release artifacts** keyed to a version, so
they build only when a version exists. Auto-versioning creates that version on the
default branch, which is why the release/build stages also key off it — gating on
"did semantic-release produce a new version?", not on the raw push.

## Auto-versioning: semantic-release + Conventional Commits

`semantic-release` reads Conventional Commit messages since the last tag and
computes the next semver: `fix:` → patch, `feat:` → minor, `feat!:` /
`BREAKING CHANGE:` → major. It writes `CHANGELOG.md`, commits it with `[skip ci]`,
creates the git tag, and publishes a GitHub/GitLab Release. `commitlint` enforces
the format on PRs/MRs so the version math stays correct.

**Why not release-please?** GitHub-native only — it would break GitLab parity.

**One host-aware config (`release.config.js`).** semantic-release auto-loads
`release.config.js`, which selects plugins by CI host (`process.env.GITLAB_CI`).
We do **not** use `--extends ./.releaserc.<host>.json`: semantic-release auto-loads
`.releaserc.json` as the *primary* config and a primary's `plugins` array silently
wins over anything passed via `--extends`, so the host overrides never took effect.
A single auto-loaded JS config that branches on the host is unambiguous.

**Neither host commits the changelog — release notes live on the Releases pages.**
Both hosts create a **tag at the real `main` HEAD plus a host Release**, and push
nothing to `main`:

- **GitHub** runs `@semantic-release/exec` + `@semantic-release/github`: writes
  `.release-version` for the build job and publishes a **GitHub Release**. It does
  **not** run `@semantic-release/git` — the `MAIN` branch ruleset (PR-required)
  rejects the CI bot's `chore(release)` commit, which would abort the whole release.
- **GitLab** runs **only** `@semantic-release/gitlab`: pushes the tag and creates a
  **GitLab Release**. Needs a `GITLAB_TOKEN` (Project Access Token, `api` scope)
  CI/CD variable.

Why no commit at all: (1) a `CHANGELOG.md` commit on both hosts would diverge
`main`; (2) a `[skip ci]` release commit makes the *tag pipeline skip*, so no images
build — tagging the real HEAD keeps it live; (3) GitHub's branch ruleset blocks the
bot from pushing to `main` anyway. The tag ref (`refs/tags/v*`) is not gated by the
branch ruleset, so the tag push succeeds. `CHANGELOG.md` in the repo reflects history
up to the cutover; per-release notes are on each host's Releases page.

### The tag-recursion gap (important)

The two hosts differ in how the computed version reaches the image build, because
their tokens differ:

- **GitHub:** a tag pushed by the default `GITHUB_TOKEN` does **not** trigger
  another workflow (loop prevention). So the build runs in the **same** workflow:
  the `release` job exposes the version as a job output, and `build`/`build-desktop`
  `needs: release` and gate on `publish == 'true'`. A hand-pushed `v*` tag is a
  fallback path.
- **GitLab:** the `semantic-release` job (with a `GITLAB_TOKEN` Project Access
  Token) **creates the `v*` tag**, which spawns a **tag pipeline** where
  `$CI_COMMIT_TAG` is set — and the `build`/`scan` jobs run there. Branch pipelines
  never build (their rule is tag-only), so no release ⇒ no empty-version build.
  Without the token, semantic-release no-ops and GitLab simply cuts no release.

## Security gates

- **bandit** — Python SAST over `app/` at medium+ severity & confidence (`-ll -ii`).
- **Trivy filesystem** — dependency CVEs + committed secrets on every push.
- **Trivy image** — scans each built image post-push.
- All gates fail only on **HIGH/CRITICAL** with `--ignore-unfixed`, so unfixable
  upstream noise doesn't block releases while real, actionable issues do.

## Supply-chain hardening

- **Third-party GitHub Actions are pinned to a full commit SHA** (with a version
  comment), e.g. `aquasecurity/trivy-action@<sha> # v0.28.0`,
  `jlumbroso/free-disk-space@<sha> # v1.3.1`. Tag pins are mutable; SHA pins are not.
- **Dependabot** (`.github/dependabot.yml`) raises reviewable bump PRs for
  github-actions, npm, and pip so pins stay current without manual tracking.
- **The privileged Pages job uses a pinned Zensical** (`scripts/build-docs.sh`,
  `zensical==0.0.45`). The job holds `pages: write` + OIDC `id-token: write`, so an
  unpinned install would be a supply-chain risk. `id-token: write` is required by
  `actions/deploy-pages` and is kept.
- **Future hardening:** move the docs install to hash-pinned installs
  (`pip install --require-hashes -r requirements-docs.txt`, generated via
  `pip-compile --generate-hashes`). Tracked as a follow-up.

## Docs build & the internal-docs prune

Both hosts call **`scripts/build-docs.sh`** (single source of truth). It pins
Zensical, runs `zensical build --clean`, then **removes `site/superpowers`**.
Zensical 0.0.45 has no config-level path exclude, and `docs/superpowers/**`
(brainstorm specs + implementation plans) must never be published. Pruning
post-build is version-proof and survives future tooling that recreates
`docs/superpowers/`.

## Registries

| Image | GHCR | GitLab |
|-------|------|--------|
| backend | `ghcr.io/<owner>/styx-backend` | `$CI_REGISTRY_IMAGE/backend` |
| frontend | `ghcr.io/<owner>/styx-frontend` | `$CI_REGISTRY_IMAGE/frontend` |
| desktop | `ghcr.io/<owner>/styx-desktop` | `$CI_REGISTRY_IMAGE/desktop` |

Each push tags both `X.Y.Z` and `latest`.

## mypy: non-blocking baseline (and the ratchet)

The codebase never ran mypy, so blocking on day one would mean a red pipeline. mypy
runs and reports but uses `continue-on-error` (GH) / `allow_failure` (GitLab).
**Ratchet path:** (1) clear reported errors module by module; (2) tighten
`[tool.mypy]` in `backend/pyproject.toml`; (3) flip the CI step to blocking. Do this
incrementally — never big-bang.

## Desktop image (~4.5 GB)

Hosted runners are tight on disk for this image. Mitigations: a free-disk step
prunes preinstalled SDKs (GH), and the desktop build is an **isolated job** so
backend/frontend still publish if desktop fails (`allow_failure` on GitLab,
separate job on GH). For reliability, run desktop builds on a **self-hosted runner**
with ample disk — add the runner label to `build-desktop`.

**Scan scope: OS packages only.** Backend/frontend are scanned with the default
`os,library` package types — their app dependencies are ours to patch. The desktop
image is scanned with **`--pkg-types os`** (`vuln-type: os` on GH) because the bulk
of its HIGH/CRITICAL findings are vendored *inside* the browsers and IDEs (bundled
JARs, `node_modules`) — not fixable from our Dockerfile. The image still runs
`apt-get upgrade` at build time to clear fixable OS-package CVEs, and the OS-scoped
scan gates on those.

## Required secrets / settings (configure per host, never commit)

- **GitHub:** `GITHUB_TOKEN` is automatic (contents:write, packages:write). Enable
  Pages (Settings → Pages → GitHub Actions). Optional GHCR PAT only if you want
  tag-triggered re-runs to fire other workflows.
- **GitLab:** `CI_REGISTRY_USER` / `CI_REGISTRY_PASSWORD` are automatic. Add
  `GITLAB_TOKEN` (Project Access Token, `api` scope) for semantic-release Releases.
  Enable Pages.

## Local reproduction

```bash
# quality
cd backend && .venv/bin/python -m ruff check app tests && .venv/bin/python -m mypy
cd frontend && npm run build
# test
cd backend && .venv/bin/python -m pytest -q
cd frontend && npm test
# security
cd backend && .venv/bin/python -m bandit -c pyproject.toml -r app -ll -ii
trivy fs --scanners vuln,secret --severity HIGH,CRITICAL --ignore-unfixed .
# docs (pinned build + prune)
sh scripts/build-docs.sh && python3 -m http.server -d site
# release (dry run, no publish)
npx semantic-release --dry-run --extends ./.releaserc.github.json
```
