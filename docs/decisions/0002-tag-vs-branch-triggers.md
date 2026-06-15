# 0002 — Tag vs branch triggers

**Status:** Accepted (2026-06-15)

**Context:** Docs and images have different release economics.

**Decision:** Default-branch pushes deploy docs and run release automation;
versioned image builds key off the computed release version (or a manual `v*` tag).
Docs are idempotent and cheap; images are immutable artifacts tied to a version.

**Consequences:** Docs always current; images only built when a version exists.
