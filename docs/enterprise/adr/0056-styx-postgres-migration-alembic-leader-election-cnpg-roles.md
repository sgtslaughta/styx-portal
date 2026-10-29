# ADR-0056: Styx Postgres migration details

- Status: Proposed
- Date: 2026-10-28
- Decision ID: D56
- Related controls: CP-9, CP-10, SC-5, IA-5

## Context

Multi-replica Styx needs migrations, singleton background loops and shared state (ADR-0036).

Source: docs/enterprise/design.md section 5.

## Decision

Use Alembic for schema migrations. Use a Postgres advisory lock for leader election of background loops. Keep lockout and rate-limit state in Postgres. DB credentials are CNPG-managed roles with periodic rotation and rolling restart, not Vault dynamic leases. (Builder call.)

## Alternatives considered

Entries beyond those recorded in design.md are the obvious options, not documented discussion.

- Vault dynamic DB leases - extra moving part, ADR-0042 chose CNPG roles.
- Per-replica in-memory state - inconsistent lockout.

## Consequences

Positive:

- Consistent state across replicas.

Negative:

- Rotation needs rolling restarts.

Follow-up work:

- Dual-backend support for homelab (SQLite) in phase 1.
