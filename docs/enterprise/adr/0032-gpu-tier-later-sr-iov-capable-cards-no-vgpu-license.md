# ADR-0032: GPU tier later: SR-IOV-capable cards, no vGPU license

- Status: Proposed
- Date: 2026-10-28
- Decision ID: D32
- Related controls: SA-4, SC-6

## Context

GPU funding is pending; per-user licensing is unacceptable.

Source: docs/enterprise/design.md section 5.

## Decision

Plan the GPU tier around SR-IOV-capable cards (Intel Flex class) with no vGPU licensing.

## Alternatives considered

Entries beyond those recorded in design.md are the obvious options, not documented discussion.

- NVIDIA vGPU - per-user license fee.
- Whole-GPU passthrough - poor density.

## Consequences

Positive:

- No licensing fees; additive hardware.

Negative:

- Hardware/driver maturity must be validated.
- Selkies encoder support for the chosen cards is unverified.

Follow-up work:

- Proof of concept when funded (phase 6).
