# CI/CD Parity (GitHub ⇄ GitLab) + Zensical Docs + Image Release — Design

Date: 2026-06-15
Branch: `feat/cicd-parity-pipelines`
Status: Approved design (pending user spec review)

## 1. Goal

Stand up CI/CD for Styx Portal from scratch with **full logical parity** between
GitHub Actions and GitLab CI. One logical pipeline expressed in two dialects.
Deliverables:

1. Quality + test + security gates on every push / PR / MR.
2. Build & push all three container images to **both** registries on `v*` tags.
3. Container image vulnerability scanning post-build.
4. **Zensical** documentation site published to **GitHub Pages and GitLab Pages**.
5. Automated semantic version bumps + `CHANGELOG.md` via **semantic-release**
   driven by **Conventional Commits**.
6. Comprehensive docs that record the *why* behind each decision.
7. Root `README.md` shipped as a **skeleton only** — owner writes the body.

## 2. Locked Decisions

| Topic | Decision |
|-------|----------|
| Hosting model | GitHub canonical; GitLab is a **push-mirror**. Both config sets committed; each host runs its own native pipeline. |
| Image scope | All 3 images (`backend`, `frontend`, `images/desktop`) → **GHCR + GitLab Container Registry**. |
| Triggers | Tags `v*` → images. Push `main` → docs + release automation. Push/PR/MR → quality/test/security. |
| Docs | `zensical new` + migrate existing `docs/*.md` into nav; author new decision-rationale pages. |
| DRY strategy | **Native per platform**: GitHub composite actions + reusable workflows; GitLab YAML anchors + `extends`. |
| mypy rollout | **Non-blocking baseline** (`continue-on-error`) with a documented ratchet to blocking later. |
| Release tool | **semantic-release** (`@semantic-release/github` + `@semantic-release/gitlab`). |
| Bump driver | **Conventional Commits** (`feat:`→minor, `fix:`→patch, `feat!`/`BREAKING CHANGE`→major). |

## 3. Logical Pipeline (identical on both platforms)

| Stage | Trigger | Tools | Gate |
|-------|---------|-------|------|
| Quality | push, PR/MR | ruff check, mypy, frontend `tsc -b` | ruff/tsc block; **mypy non-blocking** |
| Test | push, PR/MR | pytest (474 backend tests), vitest | block |
| Security (SAST) | push, PR/MR | bandit, Trivy filesystem scan (deps + secrets) | fail on **HIGH/CRITICAL** |
| Release | push `main` | semantic-release → version + `CHANGELOG.md` + tag + GH/GitLab Release | block |
| Build images | release (computed version) / tag `v*` | buildx → 3 images → GHCR + GitLab registry, tags `X.Y.Z` + `latest` | block (desktop isolated) |
| Container scan | post-build | Trivy image scan ×3 | fail on **HIGH/CRITICAL** |
| Docs | push `main` | `zensical build --clean` → Pages | block |

### Release → image-build coupling

semantic-release tags pushed by the default CI token **do not** re-trigger another
workflow (GitHub & GitLab both suppress this to avoid recursion). Therefore:

- **Primary path:** the release job computes the next version, then drives the
  image build **in the same run** via `@semantic-release/exec` (passes
  `${nextRelease.version}` to the buildx step). No reliance on a self-triggered
  tag pipeline.
- **Fallback/manual path:** pushing a `v*` tag by hand still triggers
  `release.yml` / the GitLab `release` rule directly. Same build logic, reused.

## 4. File Layout

```
.github/
  workflows/
    ci.yml          quality + test + security        (push, pull_request)
    release.yml     semantic-release → build+push 3 images → Trivy image scan  (push main; manual tag fallback)
    docs.yml        zensical build → GitHub Pages     (push main)
  actions/
    setup-backend/  composite: checkout, python, venv, install dev deps
    setup-node/     composite: checkout, node, npm ci
.gitlab-ci.yml      stages: quality test security release pages; anchors + extends
zensical.toml       site config + nav
.releaserc.json     semantic-release config (shared by both hosts)
commitlint.config.js  Conventional Commits enforcement (PR/MR check)
docs/
  index.md          landing (migrated/intro)
  CICD.md           comprehensive pipeline rationale ("logic decisions")
  decisions/        ADR-style pages surfaced in nav
  (existing: QUICKSTART, ADMIN, GPU, WORKSTATIONS, PRODUCTION, AGENT_BUILD migrated into nav)
README.md           SKELETON only (owner writes body)
backend/pyproject.toml  add [tool.mypy], [tool.bandit]-equivalent config + dev deps (mypy, bandit)
```

`docs/superpowers/**` is **excluded** from the published Zensical site (internal
specs/plans), via nav scoping / build exclude.

## 5. Parity Mechanism (how the two stay in sync)

- Same **stage graph**, same **tool versions** (pinned), same **severity gates**.
- Platform-specific glue only:
  - Registry auth: GHCR `GITHUB_TOKEN` vs GitLab `$CI_REGISTRY_USER/$CI_REGISTRY_PASSWORD`.
  - Pages deploy: `actions/deploy-pages` vs GitLab `pages:` job + `publish: site`.
  - Release plugin: `@semantic-release/github` vs `@semantic-release/gitlab`.
- DRY within each platform via composite actions (GH) and anchors/`extends` (GitLab).
- `CICD.md` is the **single source of truth** for the stage graph; both configs
  must match it. Drift is caught in review.

## 6. Registry Layout

- GHCR: `ghcr.io/<owner>/styx-backend`, `…/styx-frontend`, `…/styx-desktop`
- GitLab: `$CI_REGISTRY_IMAGE/backend`, `…/frontend`, `…/desktop`
- Tag mapping: git tag `vX.Y.Z` → image tags `X.Y.Z` **and** `latest`.

## 7. Risk Mitigations

1. **Desktop image (~4.54 GB)** on hosted runners: add a free-disk step (prune
   preinstalled SDKs/toolchains), build desktop as an **isolated matrix leg** so
   backend/frontend still publish if the desktop runner exhausts disk/time.
   Document GitLab shared-runner limits + self-hosted runner guidance in CICD.md.
2. **mypy** on a never-typed codebase: ship non-blocking; `CICD.md` records the
   ratchet path (clear errors → flip `continue-on-error` to false).
3. **Severity gating**: bandit + Trivy fail only on HIGH/CRITICAL; lower findings
   surface as warnings / job annotations / MR reports, not hard failures.
4. **Token recursion**: documented above — release job self-drives the build;
   no dependence on tag-triggered re-runs. PAT/Project-Access-Token guidance for
   teams that *want* the tag-triggered path is documented as optional.
5. **Secrets required** (documented, not committed): `GHCR`/`GITHUB_TOKEN` (auto),
   optional GHCR PAT; GitLab `CI_REGISTRY_*` (auto) + `GITLAB_TOKEN` for releases;
   Pages enablement on both hosts.

## 8. Out of Scope

- Wiring live remotes / configuring host secrets (owner's manual step).
- Deploy-to-production CD (this is build/publish + docs, not server rollout).
- Rewriting existing doc *content* beyond migration + new decision pages.
- Root `README.md` body (skeleton only).

## 9. Testing / Validation

- YAML lint both configs (`actionlint` for GH where available; GitLab CI lint).
- `zensical build --clean` succeeds locally → `site/` produced.
- `.releaserc.json` validated with `semantic-release --dry-run` (no publish).
- ruff/pytest/frontend build still green locally before commit (per repo gate:
  `npm run build` is the frontend gate, stricter than `tsc --noEmit`).
- bandit + Trivy run locally once to confirm config + baseline severity.
```
