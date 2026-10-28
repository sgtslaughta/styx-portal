# ADR-0035: Age-off and archive to OneDrive (GCC High)

- Status: Proposed
- Date: 2026-10-28
- Decision ID: D35
- Related controls: MP-6, SI-12, CM-12, SC-28

## Context

Limited storage requires lifecycle handling of stale data while retaining CUI properly.

Source: docs/enterprise/design.md section 5.

## Decision

Home files untouched 90 days are noticed for 14 days then archived to OneDrive (GCC High); profiles unused 60 days are deleted after notice; stopped-instance volumes are reclaimed after 7 days; users may archive anytime.

## Alternatives considered

Entries beyond those recorded in design.md are the obvious options, not documented discussion.

- Silent deletion - data loss.
- Keep forever - capacity exhaustion.

## Consequences

Positive:

- Controlled storage lifecycle.

Negative:

- Transfer mechanism without a service account is unresolved (likely user-delegated OAuth).
- Files of departed users need a defined path.

Follow-up work:

- Resolve OneDrive mechanism ADR in phase 5.
