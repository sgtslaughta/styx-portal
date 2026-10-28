# ADR-0030: Image rollout: next launch, 7-day recycle, 24-hour critical CVE

- Status: Proposed
- Date: 2026-10-28
- Decision ID: D30
- Related controls: SI-2, CM-3, RA-5

## Context

Patches must not interrupt active sessions unexpectedly.

Source: docs/enterprise/design.md section 5.

## Decision

New images apply at next launch or restart. Sessions older than 7 days are recycled after warning. A critical CVE forces a rollout within 24 hours.

## Alternatives considered

Entries beyond those recorded in design.md are the obvious options, not documented discussion.

- Mid-session replacement - loses user work.
- No forced recycle - old images persist indefinitely.

## Consequences

Positive:

- Predictable, user-friendly patching.

Negative:

- Forced recycle may disrupt long-running work; warning UX needed.

Follow-up work:

- Warning mechanism in phase 3/5.
