# 0006 — Supply-chain hardening

**Status:** Accepted (2026-06-15)

**Context:** Privileged CI jobs (registry push, Pages deploy with OIDC) are
attractive supply-chain targets. Unpinned third-party actions and an unpinned
`pip install` in those jobs are mutable inputs.

**Decision:** Pin third-party GitHub Actions to a full commit SHA (with version
comment). Pin Zensical to an exact version in the shared `scripts/build-docs.sh`.
Add Dependabot (github-actions, npm, pip) for reviewable bump PRs. Keep
`id-token: write` only where consumed (`actions/deploy-pages`).

**Consequences:** Reproducible privileged jobs; immutable action inputs. Future work:
hash-pinned docs installs via `pip-compile --generate-hashes`.
