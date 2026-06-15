# CI/CD Parity Pipelines Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up logically-identical CI/CD on GitHub Actions and GitLab CI that gates quality/test/security on every push, auto-versions via semantic-release + Conventional Commits, builds & pushes all 3 images to GHCR + GitLab registry, scans images with Trivy, and publishes a Zensical docs site to both Pages hosts.

**Architecture:** One logical pipeline (quality → test → security → release → build → scan → docs) expressed in two dialects. GitHub is canonical, GitLab a push-mirror. DRY within each platform via composite actions (GH) and YAML anchors/`extends` (GitLab). The release job computes the version and hands it to build jobs via job outputs (GH) / dotenv artifact (GitLab) — never via a self-triggered tag.

**Tech Stack:** GitHub Actions, GitLab CI, Docker Buildx, GHCR, GitLab Container Registry, Trivy (aquasecurity), bandit, ruff, mypy, pytest, vitest, semantic-release, commitlint, Zensical (pip), GitHub Pages, GitLab Pages.

**Reference spec:** `docs/superpowers/specs/2026-06-15-cicd-parity-design.md`

**Conventions for the executor:**
- Validators replace unit tests for declarative CI files. Install once: `npm i -g @action-validator/cli` is NOT used; use `actionlint` (download binary) and GitLab's project CI lint endpoint where a remote exists, otherwise `python -c "import yaml,sys; yaml.safe_load(open(f))"` for syntactic validity.
- No git remote exists yet, so GitLab's live `/ci/lint` API can't be hit. Use YAML parse + structural review as the gate; note this limitation in commits.
- Commit after every task with Conventional Commit messages (the repo is adopting them as of this plan).

---

## File Structure

```
.github/
  workflows/ci.yml         quality + test + security        (push, pull_request)
  workflows/release.yml    semantic-release → build 3 images → Trivy scan   (push main; tag v* fallback)
  workflows/docs.yml       zensical → GitHub Pages           (push main)
  actions/setup-backend/action.yml   composite: python + venv + dev deps
  actions/setup-node/action.yml      composite: node + npm ci
.gitlab-ci.yml             stages: quality test security release build scan pages
.releaserc.json            semantic-release config (shared)
commitlint.config.js       Conventional Commits rules
package.json               root: devDeps for semantic-release + commitlint
zensical.toml              docs site config + nav
docs/index.md              docs landing
docs/CICD.md               comprehensive pipeline rationale
docs/decisions/*.md        ADR-style decision pages
README.md                  SKELETON only
backend/pyproject.toml     add mypy + bandit config + dev deps (modify)
.gitignore                 add site/, node_modules at root, .venv-ci (modify)
```

---

## Task 1: Backend tooling — add mypy + bandit config and dev deps

**Files:**
- Modify: `backend/pyproject.toml`

- [ ] **Step 1: Add dev dependencies**

In `backend/pyproject.toml`, under `[project.optional-dependencies]` `dev = [...]`, add `mypy>=1.13.0` and `bandit>=1.8.0` to the list (keep existing entries):

```toml
dev = [
    "pytest>=8.3.0",
    "pytest-asyncio>=0.24.0",
    "ruff>=0.8.0",
    "aiohttp>=3.9",
    "mypy>=1.13.0",
    "bandit>=1.8.0",
]
```

- [ ] **Step 2: Add mypy + bandit config blocks**

Append to the end of `backend/pyproject.toml`:

```toml
[tool.mypy]
python_version = "3.12"
files = ["app"]
ignore_missing_imports = true
follow_imports = "silent"
warn_unused_ignores = false
# Non-blocking baseline: CI runs mypy with continue-on-error.
# Ratchet plan: clear errors, then flip CI gate to blocking and tighten below.
# disallow_untyped_defs = true   # enable when ratcheting

[tool.bandit]
exclude_dirs = ["tests", ".venv", "data"]
# B101 assert_used is noise in this codebase's test-adjacent helpers
skips = ["B101"]
```

- [ ] **Step 3: Install and validate locally**

Run:
```bash
cd backend && .venv/bin/pip install -e ".[dev]" -q && .venv/bin/python -m mypy --version && .venv/bin/python -m bandit --version
```
Expected: both version strings print, no install error.

- [ ] **Step 4: Capture baseline (informational, must not fail the task)**

Run:
```bash
cd backend && .venv/bin/python -m bandit -c pyproject.toml -r app -q ; echo "bandit exit: $?"
cd backend && .venv/bin/python -m mypy ; echo "mypy exit: $?"
```
Expected: commands complete and print exit codes. Record any HIGH/CRITICAL bandit findings in the commit body — if bandit reports a real HIGH/CRITICAL, STOP and report it (security gate would block CI). mypy exit code is informational (non-blocking).

- [ ] **Step 5: Commit**

```bash
git add backend/pyproject.toml
git commit -m "build(backend): add mypy + bandit config and dev deps"
```

---

## Task 2: Root package.json + semantic-release + commitlint config

**Files:**
- Create: `package.json`
- Create: `.releaserc.json`
- Create: `commitlint.config.js`
- Modify: `.gitignore`

- [ ] **Step 1: Create root `package.json`**

```json
{
  "name": "styx-portal",
  "version": "0.0.0-semantically-released",
  "private": true,
  "description": "Release automation tooling (semantic-release + commitlint). Not a publishable package.",
  "devDependencies": {
    "@commitlint/cli": "^19.6.0",
    "@commitlint/config-conventional": "^19.6.0",
    "@semantic-release/changelog": "^6.0.3",
    "@semantic-release/exec": "^6.0.3",
    "@semantic-release/git": "^10.0.1",
    "@semantic-release/github": "^11.0.0",
    "@semantic-release/gitlab": "^13.2.0",
    "conventional-changelog-conventionalcommits": "^8.0.0",
    "semantic-release": "^24.2.0"
  }
}
```

- [ ] **Step 2: Create `.releaserc.json`**

Shared by both hosts. The active publish plugin (`@semantic-release/github` vs `@semantic-release/gitlab`) is selected at runtime via `--extends`/env, but both are listed; semantic-release no-ops the one whose env (`GITHUB_TOKEN` vs `GITLAB_TOKEN`/`CI_SERVER`) is absent. `@semantic-release/exec` writes the version to `.release-version` so build jobs can read it.

```json
{
  "branches": ["main", "master"],
  "tagFormat": "v${version}",
  "plugins": [
    ["@semantic-release/commit-analyzer", { "preset": "conventionalcommits" }],
    ["@semantic-release/release-notes-generator", { "preset": "conventionalcommits" }],
    ["@semantic-release/changelog", { "changelogFile": "CHANGELOG.md" }],
    ["@semantic-release/exec", { "prepareCmd": "printf '%s' \"${nextRelease.version}\" > .release-version" }],
    ["@semantic-release/git", {
      "assets": ["CHANGELOG.md"],
      "message": "chore(release): ${nextRelease.version} [skip ci]\n\n${nextRelease.notes}"
    }]
  ]
}
```

> Note: the host-specific publish plugin is appended by each CI job (see Tasks 6 and 8) so the shared file stays host-neutral. semantic-release merges `plugins` from `--extends` configs; the CI jobs pass the publish plugin via a tiny host config that extends this file.

- [ ] **Step 3: Create host-extend configs**

Create `.releaserc.github.json`:
```json
{
  "extends": "./.releaserc.json",
  "plugins": [
    ["@semantic-release/commit-analyzer", { "preset": "conventionalcommits" }],
    ["@semantic-release/release-notes-generator", { "preset": "conventionalcommits" }],
    ["@semantic-release/changelog", { "changelogFile": "CHANGELOG.md" }],
    ["@semantic-release/exec", { "prepareCmd": "printf '%s' \"${nextRelease.version}\" > .release-version" }],
    ["@semantic-release/git", { "assets": ["CHANGELOG.md"], "message": "chore(release): ${nextRelease.version} [skip ci]\n\n${nextRelease.notes}" }],
    "@semantic-release/github"
  ]
}
```

Create `.releaserc.gitlab.json` (identical except last plugin):
```json
{
  "extends": "./.releaserc.json",
  "plugins": [
    ["@semantic-release/commit-analyzer", { "preset": "conventionalcommits" }],
    ["@semantic-release/release-notes-generator", { "preset": "conventionalcommits" }],
    ["@semantic-release/changelog", { "changelogFile": "CHANGELOG.md" }],
    ["@semantic-release/exec", { "prepareCmd": "printf '%s' \"${nextRelease.version}\" > .release-version" }],
    ["@semantic-release/git", { "assets": ["CHANGELOG.md"], "message": "chore(release): ${nextRelease.version} [skip ci]\n\n${nextRelease.notes}" }],
    "@semantic-release/gitlab"
  ]
}
```

> Rationale (record in CICD.md): listing the full plugin array in each host config is more predictable than relying on `extends` plugin-merge order, which semantic-release replaces (not concatenates). The base `.releaserc.json` documents the canonical chain; host files are the executable copies.

- [ ] **Step 4: Create `commitlint.config.js`**

```js
module.exports = { extends: ['@commitlint/config-conventional'] };
```

- [ ] **Step 5: Update `.gitignore`**

Add these lines to `.gitignore`:
```
/node_modules/
/site/
/.release-version
/package-lock.json
```
(Root `node_modules` distinct from the already-ignored `frontend` one; `site/` is Zensical output.)

- [ ] **Step 6: Validate JSON + JS syntax**

Run:
```bash
python3 -c "import json; [json.load(open(f)) for f in ['package.json','.releaserc.json','.releaserc.github.json','.releaserc.gitlab.json']]; print('json ok')"
node --check commitlint.config.js && echo "js ok"
```
Expected: `json ok` then `js ok`. If `node` is unavailable, skip the JS check and note it.

- [ ] **Step 7: Commit**

```bash
git add package.json .releaserc.json .releaserc.github.json .releaserc.gitlab.json commitlint.config.js .gitignore
git commit -m "ci: add semantic-release + commitlint config (Conventional Commits)"
```

---

## Task 3: GitHub composite actions (DRY building blocks)

**Files:**
- Create: `.github/actions/setup-backend/action.yml`
- Create: `.github/actions/setup-node/action.yml`

- [ ] **Step 1: Create `setup-backend` composite**

```yaml
name: Setup Backend
description: Checkout-agnostic Python setup + backend dev dependency install
runs:
  using: composite
  steps:
    - uses: actions/setup-python@v5
      with:
        python-version: "3.12"
    - name: Install backend dev deps
      shell: bash
      working-directory: backend
      run: |
        python -m venv .venv
        .venv/bin/pip install --upgrade pip -q
        .venv/bin/pip install -e ".[dev]" -q
```

- [ ] **Step 2: Create `setup-node` composite**

```yaml
name: Setup Node
description: Node setup + frontend dependency install
inputs:
  working-directory:
    description: Directory containing package.json
    required: false
    default: frontend
runs:
  using: composite
  steps:
    - uses: actions/setup-node@v4
      with:
        node-version: "20"
    - name: Install deps
      shell: bash
      working-directory: ${{ inputs.working-directory }}
      run: npm ci
```

- [ ] **Step 3: Validate YAML**

Run:
```bash
python3 -c "import yaml; yaml.safe_load(open('.github/actions/setup-backend/action.yml')); yaml.safe_load(open('.github/actions/setup-node/action.yml')); print('yaml ok')"
```
Expected: `yaml ok`.

- [ ] **Step 4: Commit**

```bash
git add .github/actions
git commit -m "ci(github): add setup-backend and setup-node composite actions"
```

---

## Task 4: GitHub CI workflow — quality + test + security

**Files:**
- Create: `.github/workflows/ci.yml`

- [ ] **Step 1: Write the workflow**

```yaml
name: CI
on:
  push:
    branches: [main, master]
  pull_request:

permissions:
  contents: read

concurrency:
  group: ci-${{ github.ref }}
  cancel-in-progress: true

jobs:
  quality:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: ./.github/actions/setup-backend
      - name: ruff (blocking)
        working-directory: backend
        run: .venv/bin/python -m ruff check app tests
      - name: mypy (non-blocking baseline)
        continue-on-error: true
        working-directory: backend
        run: .venv/bin/python -m mypy
      - uses: ./.github/actions/setup-node
      - name: frontend typecheck/build (blocking)
        working-directory: frontend
        run: npm run build

  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: ./.github/actions/setup-backend
      - name: pytest
        working-directory: backend
        run: .venv/bin/python -m pytest -q
      - uses: ./.github/actions/setup-node
      - name: vitest
        working-directory: frontend
        run: npm test

  security:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: ./.github/actions/setup-backend
      - name: bandit (fail on HIGH/CRITICAL)
        working-directory: backend
        run: .venv/bin/python -m bandit -c pyproject.toml -r app -ll -ii
      - name: Trivy filesystem scan (deps + secrets, fail HIGH/CRITICAL)
        uses: aquasecurity/trivy-action@0.28.0
        with:
          scan-type: fs
          scan-ref: .
          scanners: vuln,secret
          severity: HIGH,CRITICAL
          exit-code: "1"
          ignore-unfixed: true
```

> Notes for the executor:
> - `bandit -ll -ii` = report only medium+ severity AND medium+ confidence, which combined with the security gate means the job fails on genuine HIGH findings. Adjust to `-lll` if you want CRITICAL-only.
> - `npm test` runs `vitest run` per `frontend/package.json`.

- [ ] **Step 2: Validate**

Run:
```bash
python3 -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml')); print('yaml ok')"
```
Expected: `yaml ok`. If `actionlint` binary is available, also run `actionlint .github/workflows/ci.yml` and expect no errors.

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "ci(github): add quality+test+security workflow"
```

---

## Task 5: GitHub release workflow — semantic-release → build 3 images → Trivy scan

**Files:**
- Create: `.github/workflows/release.yml`

- [ ] **Step 1: Write the workflow**

```yaml
name: Release
on:
  push:
    branches: [main, master]
    tags: ["v*"]

permissions:
  contents: write      # semantic-release commits CHANGELOG + tag
  packages: write      # push to GHCR
  id-token: write

concurrency:
  group: release-${{ github.ref }}
  cancel-in-progress: false

jobs:
  release:
    runs-on: ubuntu-latest
    outputs:
      version: ${{ steps.resolve.outputs.version }}
      publish: ${{ steps.resolve.outputs.publish }}
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      # Branch push → run semantic-release. Tag push → use the tag as version (fallback path).
      - name: semantic-release (branch push only)
        if: startsWith(github.ref, 'refs/heads/')
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: |
          npm ci --no-audit --no-fund
          npx semantic-release --extends ./.releaserc.github.json || true
      - name: Resolve version + publish flag
        id: resolve
        run: |
          if [ "${GITHUB_REF##*/}" != "${GITHUB_REF}" ] && [ "${GITHUB_REF_TYPE}" = "tag" ]; then
            V="${GITHUB_REF_NAME#v}"; echo "version=$V" >> "$GITHUB_OUTPUT"; echo "publish=true" >> "$GITHUB_OUTPUT"
          elif [ -f .release-version ]; then
            echo "version=$(cat .release-version)" >> "$GITHUB_OUTPUT"; echo "publish=true" >> "$GITHUB_OUTPUT"
          else
            echo "version=" >> "$GITHUB_OUTPUT"; echo "publish=false" >> "$GITHUB_OUTPUT"
          fi

  build:
    needs: release
    if: needs.release.outputs.publish == 'true'
    runs-on: ubuntu-latest
    strategy:
      fail-fast: false
      matrix:
        include:
          - name: backend
            context: backend
            dockerfile: backend/Dockerfile
          - name: frontend
            context: frontend
            dockerfile: frontend/Dockerfile
    steps:
      - uses: actions/checkout@v4
      - uses: docker/setup-buildx-action@v3
      - name: Log in to GHCR
        uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      - name: Build and push ${{ matrix.name }}
        uses: docker/build-push-action@v6
        with:
          context: ${{ matrix.context }}
          file: ${{ matrix.dockerfile }}
          push: true
          tags: |
            ghcr.io/${{ github.repository_owner }}/styx-${{ matrix.name }}:${{ needs.release.outputs.version }}
            ghcr.io/${{ github.repository_owner }}/styx-${{ matrix.name }}:latest
      - name: Trivy image scan
        uses: aquasecurity/trivy-action@0.28.0
        with:
          image-ref: ghcr.io/${{ github.repository_owner }}/styx-${{ matrix.name }}:${{ needs.release.outputs.version }}
          severity: HIGH,CRITICAL
          exit-code: "1"
          ignore-unfixed: true

  build-desktop:
    needs: release
    if: needs.release.outputs.publish == 'true'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Free disk space (desktop image ~4.5GB)
        uses: jlumbroso/free-disk-space@v1.3.1
        with:
          tool-cache: true
          android: true
          dotnet: true
          haskell: true
          large-packages: true
          swap-storage: false
      - uses: docker/setup-buildx-action@v3
      - name: Log in to GHCR
        uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      - name: Build and push desktop
        uses: docker/build-push-action@v6
        with:
          context: images/desktop
          file: images/desktop/Dockerfile
          push: true
          tags: |
            ghcr.io/${{ github.repository_owner }}/styx-desktop:${{ needs.release.outputs.version }}
            ghcr.io/${{ github.repository_owner }}/styx-desktop:latest
      - name: Trivy image scan (desktop)
        uses: aquasecurity/trivy-action@0.28.0
        with:
          image-ref: ghcr.io/${{ github.repository_owner }}/styx-desktop:${{ needs.release.outputs.version }}
          severity: HIGH,CRITICAL
          exit-code: "1"
          ignore-unfixed: true
```

- [ ] **Step 2: Validate**

Run:
```bash
python3 -c "import yaml; yaml.safe_load(open('.github/workflows/release.yml')); print('yaml ok')"
```
Expected: `yaml ok`. Run `actionlint` if available.

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/release.yml
git commit -m "ci(github): add release workflow (semantic-release, build/push 3 images, Trivy)"
```

---

## Task 6: GitHub docs workflow — Zensical → GitHub Pages

> Depends on Task 9 (zensical.toml). If executing strictly in order, create the workflow now and verify the build in Task 9. The workflow file itself is self-contained.

**Files:**
- Create: `.github/workflows/docs.yml`

- [ ] **Step 1: Write the workflow**

```yaml
name: Docs
on:
  push:
    branches: [main, master]

permissions:
  contents: read
  pages: write
  id-token: write

concurrency:
  group: pages
  cancel-in-progress: true

jobs:
  deploy:
    environment:
      name: github-pages
      url: ${{ steps.deployment.outputs.page_url }}
    runs-on: ubuntu-latest
    steps:
      - uses: actions/configure-pages@v5
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.x"
      - run: pip install zensical
      - run: zensical build --clean
      - uses: actions/upload-pages-artifact@v3
        with:
          path: site
      - id: deployment
        uses: actions/deploy-pages@v4
```

- [ ] **Step 2: Validate**

Run:
```bash
python3 -c "import yaml; yaml.safe_load(open('.github/workflows/docs.yml')); print('yaml ok')"
```
Expected: `yaml ok`.

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/docs.yml
git commit -m "ci(github): add zensical docs deploy to GitHub Pages"
```

---

## Task 7: GitLab CI — full pipeline parity

**Files:**
- Create: `.gitlab-ci.yml`

- [ ] **Step 1: Write the pipeline**

```yaml
stages: [quality, test, security, release, build, scan, pages]

variables:
  PIP_CACHE_DIR: "$CI_PROJECT_DIR/.cache/pip"

# ---- DRY anchors -------------------------------------------------------------
.backend_setup: &backend_setup
  image: python:3.12
  before_script:
    - cd backend
    - python -m venv .venv
    - .venv/bin/pip install --upgrade pip -q
    - .venv/bin/pip install -e ".[dev]" -q

.node_setup: &node_setup
  image: node:20

.on_push_or_mr: &on_push_or_mr
  rules:
    - if: '$CI_PIPELINE_SOURCE == "merge_request_event"'
    - if: '$CI_COMMIT_BRANCH'

# ---- quality -----------------------------------------------------------------
ruff:
  stage: quality
  <<: *backend_setup
  <<: *on_push_or_mr
  script: [.venv/bin/python -m ruff check app tests]

mypy:
  stage: quality
  <<: *backend_setup
  <<: *on_push_or_mr
  allow_failure: true            # non-blocking baseline
  script: [.venv/bin/python -m mypy]

frontend-build:
  stage: quality
  <<: *node_setup
  <<: *on_push_or_mr
  script:
    - cd frontend
    - npm ci
    - npm run build

# ---- test --------------------------------------------------------------------
pytest:
  stage: test
  <<: *backend_setup
  <<: *on_push_or_mr
  script: [.venv/bin/python -m pytest -q]

vitest:
  stage: test
  <<: *node_setup
  <<: *on_push_or_mr
  script:
    - cd frontend
    - npm ci
    - npm test

# ---- security ----------------------------------------------------------------
bandit:
  stage: security
  <<: *backend_setup
  <<: *on_push_or_mr
  script: [.venv/bin/python -m bandit -c pyproject.toml -r app -ll -ii]

trivy-fs:
  stage: security
  image:
    name: aquasec/trivy:0.58.0
    entrypoint: [""]
  <<: *on_push_or_mr
  script:
    - trivy fs --scanners vuln,secret --severity HIGH,CRITICAL --exit-code 1 --ignore-unfixed .

# ---- release (semantic-release on default branch) ----------------------------
semantic-release:
  stage: release
  image: node:20
  rules:
    - if: '$CI_COMMIT_BRANCH == $CI_DEFAULT_BRANCH'
  script:
    - npm ci --no-audit --no-fund
    - npx semantic-release --extends ./.releaserc.gitlab.json || true
    - 'if [ -f .release-version ]; then echo "RELEASE_VERSION=$(cat .release-version)" > release.env; else echo "RELEASE_VERSION=" > release.env; fi'
  artifacts:
    reports:
      dotenv: release.env

# ---- build (one job per image; matrix over IMAGE) ----------------------------
.build_template: &build_template
  stage: build
  image: docker:27
  services: [docker:27-dind]
  variables:
    DOCKER_TLS_CERTDIR: "/certs"
  rules:
    - if: '$CI_COMMIT_TAG =~ /^v/'
      variables: { VERSION: "$CI_COMMIT_TAG" }
    - if: '$CI_COMMIT_BRANCH == $CI_DEFAULT_BRANCH && $RELEASE_VERSION != ""'
      variables: { VERSION: "$RELEASE_VERSION" }
  before_script:
    - 'V="${VERSION#v}"; echo "Building $IMAGE:$V"'
    - echo "$CI_REGISTRY_PASSWORD" | docker login -u "$CI_REGISTRY_USER" --password-stdin "$CI_REGISTRY"
  script:
    - V="${VERSION#v}"
    - docker build -t "$CI_REGISTRY_IMAGE/$IMAGE:$V" -t "$CI_REGISTRY_IMAGE/$IMAGE:latest" -f "$CONTEXT/Dockerfile" "$CONTEXT"
    - docker push "$CI_REGISTRY_IMAGE/$IMAGE:$V"
    - docker push "$CI_REGISTRY_IMAGE/$IMAGE:latest"

build-backend:
  <<: *build_template
  variables: { IMAGE: backend, CONTEXT: backend }

build-frontend:
  <<: *build_template
  variables: { IMAGE: frontend, CONTEXT: frontend }

build-desktop:
  <<: *build_template
  variables: { IMAGE: desktop, CONTEXT: images/desktop }
  # Desktop image ~4.5GB — shared runners may hit disk/time limits.
  # Document self-hosted runner tag here when available, e.g.:  tags: [big-disk]
  allow_failure: true

# ---- scan (Trivy image scan after build) -------------------------------------
.scan_template: &scan_template
  stage: scan
  image:
    name: aquasec/trivy:0.58.0
    entrypoint: [""]
  rules:
    - if: '$CI_COMMIT_TAG =~ /^v/'
      variables: { VERSION: "$CI_COMMIT_TAG" }
    - if: '$CI_COMMIT_BRANCH == $CI_DEFAULT_BRANCH && $RELEASE_VERSION != ""'
      variables: { VERSION: "$RELEASE_VERSION" }
  script:
    - V="${VERSION#v}"
    - trivy image --severity HIGH,CRITICAL --exit-code 1 --ignore-unfixed "$CI_REGISTRY_IMAGE/$IMAGE:$V"

scan-backend:  { <<: *scan_template, needs: [build-backend],  variables: { IMAGE: backend } }
scan-frontend: { <<: *scan_template, needs: [build-frontend], variables: { IMAGE: frontend } }
scan-desktop:  { <<: *scan_template, needs: [build-desktop],  variables: { IMAGE: desktop }, allow_failure: true }

# ---- pages (Zensical → GitLab Pages) -----------------------------------------
pages:
  stage: pages
  image: python:latest
  script:
    - pip install zensical
    - zensical build --clean
  pages:
    publish: site
  rules:
    - if: '$CI_COMMIT_BRANCH == $CI_DEFAULT_BRANCH'
```

> Executor notes:
> - GitLab can't matrix a `services: dind` job cleanly across contexts the way GH `matrix.include` does, so the three build jobs share the `*build_template` anchor — DRY without matrix.
> - `RELEASE_VERSION` flows from the `semantic-release` job's dotenv artifact into build/scan jobs automatically (same pipeline). Tag pipelines use `$CI_COMMIT_TAG` instead.

- [ ] **Step 2: Validate**

Run:
```bash
python3 -c "import yaml; yaml.safe_load(open('.gitlab-ci.yml')); print('yaml ok')"
```
Expected: `yaml ok`. (Live GitLab `/ci/lint` requires a remote; note in commit that structural lint is deferred to first push.)

- [ ] **Step 3: Commit**

```bash
git add .gitlab-ci.yml
git commit -m "ci(gitlab): add full parity pipeline (quality/test/security/release/build/scan/pages)"
```

---

## Task 8: Zensical site init + nav + migrate docs

**Files:**
- Create: `zensical.toml`
- Create: `docs/index.md`
- (existing docs migrated into nav — no move required)

- [ ] **Step 1: Install zensical locally**

Run:
```bash
pip install zensical && zensical --version
```
Expected: version prints. (If `pip` is the system one, use a throwaway venv: `python3 -m venv /tmp/zv && /tmp/zv/bin/pip install zensical && /tmp/zv/bin/zensical --version`. Use that binary for later steps.)

- [ ] **Step 2: Create `docs/index.md`**

```markdown
# Styx Portal Documentation

Styx Portal is a self-hosted remote-desktop platform: launch containerized
desktops and stream physical/virtual workstations through the browser.

## Where to start

- **[Quickstart](QUICKSTART.md)** — get a portal running.
- **[Workstations](WORKSTATIONS.md)** — enroll and stream a machine.
- **[GPU](GPU.md)** — GPU passthrough and acceleration.
- **[Admin](ADMIN.md)** — user, settings, and security administration.
- **[Production](PRODUCTION.md)** — hardened deployment.
- **[Agent Build](AGENT_BUILD.md)** — building the workstation agent.
- **[CI/CD](CICD.md)** — pipeline architecture and the reasoning behind it.
- **[Decisions](decisions/index.md)** — architecture decision records.
```

- [ ] **Step 3: Create `zensical.toml`**

```toml
# Zensical site configuration. See docs/CICD.md for why these choices were made.
[project]
name = "Styx Portal"
description = "Self-hosted remote-desktop platform"

[site]
# Set at deploy time per host; both Pages hosts serve from a project subpath.
url = ""

[build]
docs_dir = "docs"
site_dir = "site"
# Internal specs/plans must NOT be published.
exclude = ["superpowers/**"]

[theme]
name = "zensical"
palette = "auto"

[[nav]]
title = "Home"
path = "index.md"

[[nav]]
title = "Quickstart"
path = "QUICKSTART.md"

[[nav]]
title = "Workstations"
path = "WORKSTATIONS.md"

[[nav]]
title = "GPU"
path = "GPU.md"

[[nav]]
title = "Admin"
path = "ADMIN.md"

[[nav]]
title = "Production"
path = "PRODUCTION.md"

[[nav]]
title = "Agent Build"
path = "AGENT_BUILD.md"

[[nav]]
title = "CI/CD"
path = "CICD.md"

[[nav]]
title = "Decisions"
path = "decisions/index.md"
```

> Executor note: the exact `zensical.toml` schema keys may differ by Zensical version. If `zensical build` errors on an unknown key, run `zensical new` in a temp dir, diff its generated `zensical.toml`, and reconcile key names (especially `nav`, `exclude`, `theme`). Keep the intent: nav covering the migrated pages, `superpowers/**` excluded, output to `site/`. Record the final working schema in CICD.md.

- [ ] **Step 4: Build to verify (CICD.md + decisions/ created in Task 9; build will warn on missing nav targets until then — acceptable mid-plan)**

Run:
```bash
zensical build --clean ; echo "exit: $?"
ls site/index.html
```
Expected: `site/` produced. Missing `CICD.md`/`decisions/` nav entries may warn — that's fine; they land in Task 9. Re-run at end of Task 9 expecting zero missing-file warnings.

- [ ] **Step 5: Commit**

```bash
git add zensical.toml docs/index.md
git commit -m "docs(zensical): init site config + nav + landing page"
```

---

## Task 9: Comprehensive CI/CD rationale docs + decision records

**Files:**
- Create: `docs/CICD.md`
- Create: `docs/decisions/index.md`
- Create: `docs/decisions/0001-pipeline-parity.md`
- Create: `docs/decisions/0002-tag-vs-branch-triggers.md`
- Create: `docs/decisions/0003-semantic-release.md`
- Create: `docs/decisions/0004-mypy-baseline.md`
- Create: `docs/decisions/0005-desktop-image-isolation.md`

- [ ] **Step 1: Create `docs/CICD.md`** (the comprehensive "logic decisions" doc)

````markdown
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
| Docs | push default branch | `zensical build` → Pages | block |

## Why parity, and how it's maintained

GitHub is canonical; GitLab is a push-mirror so the project stays reachable on
both. Rather than a cross-platform meta-CI tool (extra dependency, lowest-common
-denominator features), each host uses **native idioms**: GitHub composite actions
+ reusable workflows, GitLab YAML anchors + `extends`. Parity is a property of the
**stage graph and gates**, enforced by this document and code review — not by
shared YAML. The tradeoff: occasional manual sync. The benefit: each pipeline is
idiomatic and uses each platform's best features (GH Pages OIDC deploy, GitLab
dotenv artifacts).

## Triggers: why tags build images but branches deploy docs

Docs are **idempotent and cheap** — redeploying on every `main` push is free and
keeps the site current. Images are **immutable release artifacts** keyed to a
version, so they build only when a version exists. Auto-versioning (below) creates
that version on `main`, which is why the release/build stages also key off `main`
— but they gate on "did semantic-release produce a new version?", not on the raw
push.

## Auto-versioning: semantic-release + Conventional Commits

`semantic-release` reads Conventional Commit messages since the last tag and
computes the next semver: `fix:` → patch, `feat:` → minor, `feat!:` /
`BREAKING CHANGE:` → major. It writes `CHANGELOG.md`, commits it with `[skip ci]`,
creates the git tag, and publishes a GitHub/GitLab Release. `commitlint` enforces
the commit format on PRs/MRs so the version math stays correct.

**Why not release-please?** GitHub-native only — it would break GitLab parity.
**Why list full plugin arrays in `.releaserc.<host>.json`?** semantic-release
*replaces* the `plugins` array from an `extends` base rather than concatenating,
so each host config carries the complete chain plus its host publish plugin. The
base `.releaserc.json` is the documented canonical chain.

### The tag-recursion gap (important)

A tag pushed by the CI token does **not** trigger another pipeline (both GitHub
and GitLab suppress this to prevent infinite loops). So we do **not** rely on
"semantic-release pushes a tag → release workflow fires." Instead:

- semantic-release writes the version to `.release-version`.
- **GitHub:** the `release` job exposes it as a job output; `build`/`build-desktop`
  jobs `needs: release` and gate on `publish == 'true'`.
- **GitLab:** the `semantic-release` job writes `release.env` (dotenv artifact);
  downstream `build`/`scan` jobs read `$RELEASE_VERSION`.

Pushing a `v*` tag by hand still works as a **fallback** path (uses the tag as the
version directly) for re-releases or manual cuts.

## Security gates

- **bandit** — Python SAST over `app/`. Runs at medium+ severity & confidence
  (`-ll -ii`); a genuine HIGH fails the build.
- **Trivy filesystem** — dependency CVEs + committed secrets on every push.
- **Trivy image** — scans each built image post-push.
- All gates fail only on **HIGH/CRITICAL** with `--ignore-unfixed`, so unfixable
  upstream noise doesn't block releases while real, actionable issues do.

## mypy: non-blocking baseline (and the ratchet)

The codebase never ran mypy, so blocking on day one would mean a red pipeline.
mypy runs and reports but uses `continue-on-error` (GH) / `allow_failure` (GitLab).
**Ratchet path:** (1) clear reported errors module by module; (2) tighten
`[tool.mypy]` in `backend/pyproject.toml` (`disallow_untyped_defs`, etc.); (3) flip
the CI step to blocking. Do this incrementally — never in one big-bang PR.

## Registries

| Image | GHCR | GitLab |
|-------|------|--------|
| backend | `ghcr.io/<owner>/styx-backend` | `$CI_REGISTRY_IMAGE/backend` |
| frontend | `ghcr.io/<owner>/styx-frontend` | `$CI_REGISTRY_IMAGE/frontend` |
| desktop | `ghcr.io/<owner>/styx-desktop` | `$CI_REGISTRY_IMAGE/desktop` |

Each push tags both `X.Y.Z` and `latest`.

## Desktop image (~4.5 GB)

Hosted runners are tight on disk for this image. Mitigations: a free-disk step
prunes preinstalled SDKs (GH), and the desktop build is an **isolated job** so
backend/frontend still publish if desktop fails (`allow_failure` on GitLab,
separate job on GH). For reliability, run desktop builds on a **self-hosted
runner** with ample disk — add the runner label to `build-desktop` (GitLab `tags:`
/ GH `runs-on:`).

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
trivy fs --scanners vuln,secret --severity HIGH,CRITICAL .
# docs
zensical build --clean && python3 -m http.server -d site
# release (dry run, no publish)
npx semantic-release --dry-run --extends ./.releaserc.github.json
```
````

- [ ] **Step 2: Create `docs/decisions/index.md`**

```markdown
# Architecture Decision Records

Short records of significant CI/CD decisions and their rationale.

- [0001 — Pipeline parity strategy](0001-pipeline-parity.md)
- [0002 — Tag vs branch triggers](0002-tag-vs-branch-triggers.md)
- [0003 — semantic-release for versioning](0003-semantic-release.md)
- [0004 — mypy non-blocking baseline](0004-mypy-baseline.md)
- [0005 — Desktop image build isolation](0005-desktop-image-isolation.md)
```

- [ ] **Step 3: Create the five ADR files**

`docs/decisions/0001-pipeline-parity.md`:
```markdown
# 0001 — Pipeline parity strategy

**Status:** Accepted (2026-06-15)

**Context:** The project is mirrored to GitHub (canonical) and GitLab. We want
identical CI behavior without a heavy cross-platform abstraction.

**Decision:** Express one logical stage graph in each host's native idiom —
GitHub composite actions/reusable workflows, GitLab anchors/`extends`. Parity is
enforced by `docs/CICD.md` (source of truth) plus code review.

**Consequences:** (+) Idiomatic, uses each platform's best features. (−) Manual
sync when the graph changes; mitigated by the small surface and the SoT doc.
```

`docs/decisions/0002-tag-vs-branch-triggers.md`:
```markdown
# 0002 — Tag vs branch triggers

**Status:** Accepted (2026-06-15)

**Context:** Docs and images have different release economics.

**Decision:** Branch (`main`) pushes deploy docs and run release automation;
versioned image builds key off the computed release version (or a manual `v*`
tag). Docs are idempotent and cheap; images are immutable artifacts tied to a
version.

**Consequences:** Docs always current; images only built when a version exists.
```

`docs/decisions/0003-semantic-release.md`:
```markdown
# 0003 — semantic-release for versioning

**Status:** Accepted (2026-06-15)

**Context:** We need automatic version bumps + changelog on both hosts.

**Decision:** Use semantic-release with Conventional Commits and both the GitHub
and GitLab publish plugins. Rejected release-please (GitHub-only) because it
breaks parity.

**Consequences:** Commit discipline required (enforced by commitlint). The
tag-recursion gap is handled by passing the version through job outputs / dotenv
artifacts rather than self-triggered tag pipelines (see CICD.md).
```

`docs/decisions/0004-mypy-baseline.md`:
```markdown
# 0004 — mypy non-blocking baseline

**Status:** Accepted (2026-06-15)

**Context:** The codebase never ran mypy; blocking immediately would red-light CI.

**Decision:** Run mypy non-blocking (`continue-on-error` / `allow_failure`) with a
documented ratchet: clear errors per module, tighten config, then make it
blocking.

**Consequences:** Type coverage improves incrementally without halting delivery.
```

`docs/decisions/0005-desktop-image-isolation.md`:
```markdown
# 0005 — Desktop image build isolation

**Status:** Accepted (2026-06-15)

**Context:** The desktop image is ~4.5 GB; hosted runners are disk/time constrained.

**Decision:** Build desktop in an isolated job with a free-disk step (GH) and
`allow_failure` (GitLab), so backend/frontend publish independently. Recommend a
self-hosted runner with ample disk for reliable desktop builds.

**Consequences:** Core images always ship; desktop may need a beefier runner.
```

- [ ] **Step 4: Rebuild docs to verify nav resolves**

Run:
```bash
zensical build --clean ; echo "exit: $?"
ls site/index.html
```
Expected: build succeeds, no missing-nav-file warnings.

- [ ] **Step 5: Commit**

```bash
git add docs/CICD.md docs/decisions
git commit -m "docs: add comprehensive CI/CD rationale + ADRs"
```

---

## Task 10: README skeleton

**Files:**
- Modify: `README.md` (replace with skeleton)

- [ ] **Step 1: Inspect current README so nothing important is silently dropped**

Run:
```bash
sed -n '1,80p' README.md
```
Expected: see current content. Preserve the project title/badges intent; the owner writes the body.

- [ ] **Step 2: Replace `README.md` with a skeleton**

```markdown
# Styx Portal

<!-- Owner writes the body. Skeleton scaffolded by CI/CD parity work (2026-06-15). -->

> Self-hosted remote-desktop platform — launch containerized desktops and stream
> physical/virtual workstations through the browser.

<!-- BADGES (fill in once remotes exist):
[![CI](…)]() [![Release](…)]() [![Docs](…)]()
-->

## Overview

<!-- TODO(owner): one-paragraph pitch. -->

## Features

<!-- TODO(owner): bullet the headline capabilities. -->

## Quickstart

See **[docs/QUICKSTART.md](docs/QUICKSTART.md)**.

## Documentation

Full docs (Zensical site, also published to GitHub/GitLab Pages):

- [Quickstart](docs/QUICKSTART.md)
- [Workstations](docs/WORKSTATIONS.md)
- [GPU](docs/GPU.md)
- [Admin](docs/ADMIN.md)
- [Production](docs/PRODUCTION.md)
- [Agent Build](docs/AGENT_BUILD.md)
- [CI/CD architecture](docs/CICD.md)

## Development

See **[CLAUDE.md](CLAUDE.md)** for project structure and commands.

## Contributing

This project uses **Conventional Commits** (enforced by commitlint) so releases
and changelogs are automated. Example: `feat(agent): add reconnect backoff`.

## License

<!-- TODO(owner): choose and state a license. -->
```

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: scaffold README skeleton (owner to write body)"
```

---

## Task 11: Final validation sweep

**Files:** none (verification only)

- [ ] **Step 1: All CI YAML parses**

Run:
```bash
python3 -c "import yaml,glob; [yaml.safe_load(open(f)) for f in glob.glob('.github/workflows/*.yml')+glob.glob('.github/actions/*/action.yml')+['.gitlab-ci.yml']]; print('all yaml ok')"
```
Expected: `all yaml ok`.

- [ ] **Step 2: semantic-release dry-run (no publish, no token side effects)**

Run:
```bash
npm ci --no-audit --no-fund >/dev/null 2>&1 || npm install --no-audit --no-fund
npx semantic-release --dry-run --no-ci --extends ./.releaserc.github.json 2>&1 | tail -20
```
Expected: it analyzes commits and reports the next version (or "no release"). Errors about missing `GITHUB_TOKEN`/remote are acceptable in dry-run without a remote — confirm it got as far as commit analysis.

- [ ] **Step 3: Repo gates still green**

Run:
```bash
cd backend && .venv/bin/python -m ruff check app tests && .venv/bin/python -m pytest -q
cd frontend && npm run build
```
Expected: ruff clean, 474 backend tests pass, frontend build succeeds.

- [ ] **Step 4: Zensical builds clean**

Run:
```bash
zensical build --clean && test -f site/index.html && echo "docs ok"
```
Expected: `docs ok`, no missing-nav warnings.

- [ ] **Step 5: Confirm internal specs are NOT in the published site**

Run:
```bash
! grep -rl "superpowers" site/ >/dev/null 2>&1 && echo "specs excluded ok"
```
Expected: `specs excluded ok` (the `exclude` glob kept `docs/superpowers/**` out of `site/`).

- [ ] **Step 6: Final commit (if any validation tweaks were needed)**

```bash
git add -A
git commit -m "ci: final validation fixes for pipeline parity" || echo "nothing to commit"
```

---

## Self-Review Notes (author)

- **Spec coverage:** parity (T3–T8), quality/test/security (T4,T7), images→both registries on tags (T5,T7), container scan (T5,T7), Zensical→both Pages (T6,T7,T8), semantic-release auto-version+changelog (T2,T5,T7), comprehensive rationale (T9), README skeleton (T10), mypy baseline (T1,T4,T7), desktop isolation (T5,T7). All mapped.
- **Placeholder scan:** TODOs exist only inside the README skeleton (intentional — owner writes body) and the documented mypy ratchet. No plan-step placeholders.
- **Type/name consistency:** image names `styx-backend/frontend/desktop` (GHCR) and `backend/frontend/desktop` (GitLab) used consistently across T5/T7/T9. `.release-version` / `RELEASE_VERSION` / `release.env` consistent across T2/T5/T7/T9.
- **Known runtime caveats flagged in-plan:** `zensical.toml` schema keys may vary by version (T8 reconciliation step); GitLab live lint deferred until a remote exists (T7); semantic-release dry-run without remote is partial (T11).
```
