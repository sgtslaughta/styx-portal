# ADR-0031: CPU tier caps: 1080p, 30 fps, HiDPI off; ~3 cores and 4 GB per desktop

- Status: Proposed
- Date: 2026-10-28
- Decision ID: D31
- Related controls: SC-5, SC-6, CM-6

## Context

CPU-only encoding is expensive; capacity must be bounded until GPUs are funded.

Source: docs/enterprise/design.md section 5.

## Decision

Cap CPU-tier desktops at 1080p, 30 fps, HiDPI off, roughly 3 cores and 4 GB per concurrent desktop, with per-group override.

## Alternatives considered

Entries beyond those recorded in design.md are the obvious options, not documented discussion.

- Uncapped quality - exhausts CPU.
- Lower defaults - worse experience than needed.

## Consequences

Positive:

- Predictable capacity per session.

Negative:

- Degraded experience for demanding users until GPU tier.
- Totals imply more cores than D06 may state (see design inconsistencies).

Follow-up work:

- Validate in load test (D47).
