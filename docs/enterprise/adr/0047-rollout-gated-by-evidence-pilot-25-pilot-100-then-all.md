# ADR-0047: Rollout gated by evidence: pilot 25, pilot 100, then all users

- Status: Proposed
- Date: 2026-10-28
- Decision ID: D47
- Related controls: CA-2, CA-7, CP-4, SA-11, SC-5

## Context

Scale should follow evidence of readiness.

Source: docs/enterprise/design.md section 5.

## Decision

Pilot 25 after phase 4, 100 after phase 5, and all users after the load-test gate, which follows phase 5: 200-session synthetic soak, launch p95 under 10 s, stream p95 under 80 ms (client-side RTT metric), zero drops over 4 hours. All users no longer wait for phase 6 (GPU).

## Alternatives considered

Entries beyond those recorded in design.md are the obvious options, not documented discussion.

- Big-bang launch - unmanaged risk.
- Gate on feature completion only - no performance evidence.

## Consequences

Positive:

- Evidence before scale.

Negative:

- The 8-10 s launch target (ADR-0046) leaves little margin under the p95 < 10 s gate.

Follow-up work:

- Build load-test harness in phase 5.
