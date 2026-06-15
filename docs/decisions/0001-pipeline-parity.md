# 0001 — Pipeline parity strategy

**Status:** Accepted (2026-06-15)

**Context:** The project is mirrored to GitHub (canonical) and GitLab. We want
identical CI behavior without a heavy cross-platform abstraction.

**Decision:** Express one logical stage graph in each host's native idiom — GitHub
composite actions/reusable workflows, GitLab anchors/`extends`. Parity is enforced
by `docs/CICD.md` (source of truth) plus code review.

**Consequences:** (+) Idiomatic, uses each platform's best features. (−) Manual sync
when the graph changes; mitigated by the small surface and the SoT doc.
