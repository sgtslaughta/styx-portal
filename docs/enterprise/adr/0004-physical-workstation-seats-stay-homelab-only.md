# ADR-0004: Physical workstation seats stay homelab-only

- Status: Proposed
- Date: 2026-10-28
- Decision ID: D04
- Related controls: AC-17, CM-7

## Context

Styx can stream physical workstation seats. Enterprise remote users are all served with containerized desktops.

Source: docs/enterprise/design.md section 5.

## Decision

Physical-workstation streaming is disabled in the enterprise profile; enterprise users get container desktops only.

## Alternatives considered

Entries beyond those recorded in design.md are the obvious options, not documented discussion.

- Enable seat mode in enterprise - adds attack surface and hardware management with no user need.
- Separate product for seats - unnecessary for v1.

## Consequences

Positive:

- Smaller attack surface (least functionality).
- Simpler agent and network model.

Negative:

- Feature parity gap between profiles must be documented.

Follow-up work:

- Confirm enterprise profile compiles/ships without the workstation agent enrollment path (phase 1).
