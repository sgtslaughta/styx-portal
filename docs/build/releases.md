# Releases and CI/CD

How a commit becomes a versioned release, and how the GitHub and GitLab
pipelines stay in step. This page also holds the former `CICD.md` and the build
facts from `AGENT_BUILD.md`.

## Versioning rules

* **Conventional Commits** drive everything: `fix:` patch, `feat:` minor, `feat!:` or a `BREAKING CHANGE:` footer major.
* `commitlint` (`@commitlint/config-conventional`) checks PR/MR commits; subjects must be lowercase (no sentence/start/upper case).
* **semantic-release** runs on the default branch, computes the next version, creates the tag `vX.Y.Z` and a host Release with generated notes.
* **Nothing is committed back to `main`.** `CHANGELOG.md` reflects history up to the cutover; per-release notes live on the Releases pages. See ADRs [0002](../decisions/0002-tag-vs-branch-triggers.md) and [0003](../decisions/0003-semantic-release.md).
* `scripts/stamp-version.sh` writes the version into `backend/pyproject.toml` at image-build time; the backend reports it via `importlib.metadata`.

### Agent version stream

`AGENT_VERSION` in `agent/styx_agent.py` is **independent** of the repo release
version. It drives the workstation auto-update check (`get_latest_agent_version`
parses it). Bump it whenever `agent/**` changes behaviour; `stamp-version.sh`
deliberately never touches it, or every workstation would appear outdated.

## CI stage graph

| Stage | Trigger | Tools | Gate |
|-------|---------|-------|------|
| Quality | push, PR/MR | ruff, mypy, frontend `tsc -b` | ruff/tsc block; **mypy non-blocking** |
| Test | push, PR/MR | pytest, vitest, Go plugin test | block |
| Security | push, PR/MR | bandit, Trivy fs (vuln + secret) | fail HIGH/CRITICAL |
| Release | push to default branch | semantic-release | block |
| Build | release version / tag `v*` | buildx: backend, frontend, desktop to GHCR and GitLab registry | block (desktop isolated) |
| Scan | post-build | Trivy image x3 | fail HIGH/CRITICAL |
| Docs | push to default branch | `scripts/build-docs.sh` -> Pages | block |

![CI pipeline: quality, test and security gates, then semantic-release and docs publishing on the default branch](../assets/diagrams/build-releases-1-light.svg#only-light)
![CI pipeline: quality, test and security gates, then semantic-release and docs publishing on the default branch](../assets/diagrams/build-releases-1-dark.svg#only-dark)

### Why parity, and how it is kept

GitHub is canonical and GitLab is a push mirror. Instead of a cross-platform
meta-CI tool, each host uses its native idioms (GitHub composite actions
`.github/actions/setup-backend` and `setup-node`; GitLab anchors and `extends`).
Parity is a property of the **stage graph and gates**, enforced by this page and
code review, not shared YAML. If a workflow file and this page disagree, the
workflow is the bug. See ADR [0001](../decisions/0001-pipeline-parity.md).

### Tags build images, branches deploy docs

Docs are idempotent and cheap, so every default-branch push redeploys them.
Images are immutable artifacts keyed to a version, so they build only when a
version exists.

### One host-aware semantic-release config

`release.config.js` picks plugins by `process.env.GITLAB_CI`. A `.releaserc.json`
would be auto-loaded as the *primary* config and its `plugins` would silently
override `--extends`, which is why a single JS config is used.

* **GitHub**: `@semantic-release/exec` (writes `.release-version`, runs `stamp-version.sh`) and `@semantic-release/github`. No `@semantic-release/git`, because the `main` branch ruleset rejects a bot `chore(release)` commit.
* **GitLab**: only `@semantic-release/gitlab`; needs a `GITLAB_TOKEN` (Project Access Token, `api` scope).

!!! warning "The tag-recursion gap"
    A tag pushed with GitHub's default `GITHUB_TOKEN` does not trigger another
    workflow. So on GitHub the image build runs in the **same** workflow
    (`build` needs `release` and gates on `publish == 'true'`); a hand-pushed
    `v*` tag is the fallback. On GitLab the `semantic-release` job (with the
    token) creates the tag, which spawns a tag pipeline where `$CI_COMMIT_TAG`
    is set and `build`/`scan` run. Branch pipelines never build.

## Images and registries

| Image | GHCR | GitLab |
|-------|------|--------|
| backend | `ghcr.io/<owner>/styx-backend` | `$CI_REGISTRY_IMAGE/backend` |
| frontend | `ghcr.io/<owner>/styx-frontend` | `$CI_REGISTRY_IMAGE/frontend` |
| desktop | `ghcr.io/<owner>/styx-desktop` | `$CI_REGISTRY_IMAGE/desktop` |

Each build is tagged `X.Y.Z` and `latest`.

**Desktop image (~4.5 GB).** Hosted runners are tight on disk, so the desktop
build is an isolated job (backend and frontend still publish if it fails) with a
free-disk step on GitHub; prefer a self-hosted runner with ample disk
(ADR [0005](../decisions/0005-desktop-image-isolation.md)). Its Trivy scan uses
`--pkg-types os` because most findings are vendored inside browsers and IDEs, not
fixable from our Dockerfile; the image runs `apt-get upgrade` at build time.

## Security gates and supply chain

* **bandit** over `app/` at medium+ severity and confidence (`-ll -ii`); **Trivy fs** (vulns + secrets) on every push; **Trivy image** after each build. All fail only on HIGH/CRITICAL with `--ignore-unfixed`.
* Third-party GitHub Actions are pinned to **full commit SHAs** with a version comment; Dependabot (`.github/dependabot.yml`) raises bump PRs for actions, npm and pip.
* The privileged Pages job uses a pinned Zensical (`scripts/build-docs.sh`, `zensical==0.0.45`). `id-token: write` is required by `actions/deploy-pages`.
* Follow-up: hash-pinned docs install (`pip install --require-hashes`). See ADR [0006](../decisions/0006-supply-chain-hardening.md).

### mypy ratchet

mypy runs non-blocking (`continue-on-error` / `allow_failure`) because the
codebase never ran it. Ratchet: clear errors module by module, tighten
`[tool.mypy]` in `backend/pyproject.toml`, then flip the CI step to blocking.
Never big-bang (ADR [0004](../decisions/0004-mypy-baseline.md)).

## Docs build

Both hosts call `scripts/build-docs.sh`: pin Zensical, `zensical build --clean`,
then remove `site/superpowers` (internal specs and plans must never be
published; Zensical 0.0.45 has no config-level exclude).

```bash
sh scripts/build-docs.sh && python3 -m http.server -d site
```

## Required settings (never commit)

* **GitHub**: `GITHUB_TOKEN` is automatic. Enable Pages (GitHub Actions source). The `main` ruleset requires PRs.
* **GitLab**: registry credentials are automatic; add `GITLAB_TOKEN` (Project Access Token, `api`) and enable Pages.

## Agent artifacts and desktop images

Not released by CI. Agent code ships from the repo (`agent/` is mounted into the
backend and served at `/api/enroll/`), so releasing an agent change means
deploying the backend and bumping `AGENT_VERSION`. Server-built agent artifacts
(`wheelhouse-x86_64.tar.gz`, `nwg-shell-x86_64.tar.gz`) are produced by
`scripts/build_agent_artifacts.sh` on the portal host and copied into
`ARTIFACT_CACHE_DIR`; see [Agent](agent.md#seats).

## Local reproduction

```bash
cd backend && .venv/bin/python -m ruff check app tests && .venv/bin/python -m mypy
cd frontend && npm run build
cd backend && .venv/bin/python -m pytest -q
cd frontend && npm test
cd backend && .venv/bin/python -m bandit -c pyproject.toml -r app -ll -ii
trivy fs --scanners vuln,secret --severity HIGH,CRITICAL --ignore-unfixed .
npx semantic-release --dry-run          # no publish
```
