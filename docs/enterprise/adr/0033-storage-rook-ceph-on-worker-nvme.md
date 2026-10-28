# ADR-0033: Storage: Rook-Ceph on worker NVMe

- Status: Proposed
- Date: 2026-10-28
- Decision ID: D33
- Related controls: CP-9, SC-28, SC-5

## Context

Homes, volumes and S3 are needed with one free system.

Source: docs/enterprise/design.md section 5.

## Decision

Run Rook-Ceph on worker NVMe providing CephFS (homes and profiles), RBD (volumes) and RGW (S3, including cold archive). OSDs get per-node CPU/memory reservations (ADR-0055).

## Alternatives considered

Entries beyond those recorded in design.md are the obvious options, not documented discussion.

- Longhorn/OpenEBS plus MinIO - multiple systems.
- SAN/NAS - cost and additional vendor.

## Consequences

Positive:

- One system for file, block and object.

Negative:

- Co-location with desktop workloads competes for CPU/IO.
- Ceph operations expertise needed.

Follow-up work:

- Encryption at rest design (SC-28) and capacity planning in phase 1.
