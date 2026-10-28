# ADR-0009: Sizing: 150-200 concurrent desktops at peak

- Status: Proposed
- Date: 2026-10-28
- Decision ID: D09
- Related controls: CP-2, SC-5

## Context

About 30-40% of 500 users are expected concurrently in an office-hours pattern (owner estimate).

Source: docs/enterprise/design.md section 5.

## Decision

Size the platform for 150-200 concurrent desktops, validated by the load-test gate (D47, 200-session soak). Figures are per worker: 8 workers x 128 cores / 512 GB. N-1 budget: 7 surviving workers x 128 = 896 cores must cover 200 desktops x 3 cores (600), Ceph OSD reservations (~4 cores per node, ADR-0055) and platform services (~100 cores); about 170 cores spare.

## Alternatives considered

Entries beyond those recorded in design.md are the obvious options, not documented discussion.

- Size for all 500 concurrent - cost-prohibitive.
- Size for average load - fails at peak.

## Consequences

Positive:

- Clear capacity target for procurement and load tests.

Negative:

- Estimate is unvalidated; headroom needs monitoring.
- Memory budget (7 x 512 GB against 200 x 4 GB plus platform) must be re-checked with real usage.

Follow-up work:

- Revisit after pilots using real usage data.
