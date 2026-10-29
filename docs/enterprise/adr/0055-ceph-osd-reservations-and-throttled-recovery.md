# ADR-0055: Ceph OSD reservations and throttled recovery

- Status: Proposed
- Date: 2026-10-28
- Decision ID: D55
- Related controls: SC-5, CP-2

## Context

Ceph shares worker nodes with desktops (ADR-0033).

Source: docs/enterprise/design.md section 5.

## Decision

Reserve CPU and memory per node for OSDs, and throttle recovery/backfill during business hours. (Builder call.)

## Alternatives considered

Entries beyond those recorded in design.md are the obvious options, not documented discussion.

- No reservation - desktops starve OSDs.
- Dedicated storage nodes - more hardware.

## Consequences

Positive:

- Storage stays responsive under load.

Negative:

- Slower recovery in business hours.

Follow-up work:

- Tune and test under the load gate.
