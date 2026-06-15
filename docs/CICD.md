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
**Why list full plugin arrays in `.releaserc.<host>.json`?** semantic-release
*replaces* the `plugins` array from an `extends` base rather than concatenating, so
each host config carries the complete chain plus its host publish plugin. The base
`.releaserc.json` is the documented canonical chain.

### The tag-recursion gap (important)

A tag pushed by the CI token does **not** trigger another pipeline (both GitHub and
GitLab suppress this to prevent loops). So we do **not** rely on "semantic-release
pushes a tag → release workflow fires." Instead:

- semantic-release writes the version to `.release-version`.
- **GitHub:** the `release` job exposes it as a job output; `build`/`build-desktop`
  jobs `needs: release` and gate on `publish == 'true'`.
- **GitLab:** the `semantic-release` job writes `release.env` (dotenv artifact);
  downstream `build`/`scan` jobs read `$RELEASE_VERSION`.

Pushing a `v*` tag by hand still works as a **fallback** (uses the tag as the
version directly) for re-releases or manual cuts.

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
