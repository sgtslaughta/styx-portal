# 0004 — mypy non-blocking baseline

**Status:** Accepted (2026-06-15)

**Context:** The codebase never ran mypy; blocking immediately would red-light CI.

**Decision:** Run mypy non-blocking (`continue-on-error` / `allow_failure`) with a
documented ratchet: clear errors per module, tighten config, then make it blocking.

**Consequences:** Type coverage improves incrementally without halting delivery.
