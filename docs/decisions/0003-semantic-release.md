# 0003 — semantic-release for versioning

**Status:** Accepted (2026-06-15)

**Context:** We need automatic version bumps + changelog on both hosts.

**Decision:** Use semantic-release with Conventional Commits and both the GitHub and
GitLab publish plugins. Rejected release-please (GitHub-only) because it breaks
parity.

**Consequences:** Commit discipline required (enforced by commitlint). The
tag-recursion gap is handled by passing the version through job outputs / dotenv
artifacts rather than self-triggered tag pipelines (see CICD.md).
