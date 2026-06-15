# 0005 — Desktop image build isolation

**Status:** Accepted (2026-06-15)

**Context:** The desktop image is ~4.5 GB; hosted runners are disk/time constrained.

**Decision:** Build desktop in an isolated job with a free-disk step (GH) and
`allow_failure` (GitLab), so backend/frontend publish independently. Recommend a
self-hosted runner with ample disk for reliable desktop builds.

**Consequences:** Core images always ship; desktop may need a beefier runner.
