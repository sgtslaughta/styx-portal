# ADR-0009: Sizing: 150-200 concurrent desktops at peak

- Status: Proposed
- Date: 2026-10-28
- Decision ID: D09
- Related controls: CP-2, SC-5

## Context

About 30-40% of 500 users are expected concurrently in an office-hours pattern (owner estimate).

Source: docs/enterprise/design.md section 5.

## Decision

Size the platform for 150-200 concurrent desktops, validated by the load-test gate (D47).

## Alternatives considered

Entries beyond those recorded in design.md are the obvious options, not documented discussion.

- Size for all 500 concurrent - cost-prohibitive.
- Size for average load - fails at peak.

## Consequences

Positive:

- Clear capacity target for procurement and load tests.

Negative:

- Estimate is unvalidated; headroom needs monitoring.
- See D06/D31 for an arithmetic consistency note.

Follow-up work:

- Revisit after pilots using real usage data.
