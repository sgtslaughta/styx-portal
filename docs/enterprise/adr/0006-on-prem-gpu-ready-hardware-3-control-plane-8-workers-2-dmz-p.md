# ADR-0006: On-prem GPU-ready hardware: 3 control plane, 8 workers, 2 DMZ proxies

- Status: Proposed
- Date: 2026-10-28
- Decision ID: D06
- Related controls: CP-2, PE-3, SC-7, SA-4

## Context

Hosting is on-prem on new enterprise hardware at one site. GPU funding comes later; the first release is CPU-only but must not need re-architecture when GPUs arrive.

Source: docs/enterprise/design.md section 5.

## Decision

Procure 3 control-plane nodes, 8 workers (each 128 cores and 512 GB RAM) and 2 DMZ proxy hosts, specified so GPU cards can be added later.

## Alternatives considered

Entries beyond those recorded in design.md are the obvious options, not documented discussion.

- Cloud hosting - on-prem is a stated constraint.
- CPU-only chassis - would force new servers when GPU is funded.
- Fewer, larger nodes - larger failure domain per node.

## Consequences

Positive:

- GPU funding means adding cards, not servers.
- Control-plane quorum with 3 nodes.

Negative:

- Single site: no site-level DR (see D37).
- Physical controls are inherited from the hosting facility.

Follow-up work:

- Capacity check against D09/D31 holds on paper (N-1 budget in ADR-0009); confirm in the phase 1 load tests.
