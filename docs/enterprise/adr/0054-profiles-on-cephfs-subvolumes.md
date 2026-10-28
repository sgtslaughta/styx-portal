# ADR-0054: Profiles on CephFS subvolumes

- Status: Proposed
- Date: 2026-10-28
- Decision ID: D54
- Related controls: CP-9, CP-10, CM-12

## Context

RBD volumes are RWO and slow to reattach after node loss.

Source: docs/enterprise/design.md section 5.

## Decision

Per-app profiles move from RBD to CephFS subvolumes (RWX) that reattach after node loss. Non-graceful node-shutdown handling is automated. (Builder call.)

## Alternatives considered

Entries beyond those recorded in design.md are the obvious options, not documented discussion.

- Keep RBD - reattach delays and RWO limits.

## Consequences

Positive:

- Faster recovery; no volume pinning.

Negative:

- Shared filesystem load on MDS; profile databases (for example browser SQLite) need testing on CephFS.

Follow-up work:

- Validate with the supported browser images in phase 3.
