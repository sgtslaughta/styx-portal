# ADR-0036: Styx database: SQLite to PostgreSQL via CloudNativePG

- Status: Proposed
- Date: 2026-10-28
- Decision ID: D36
- Related controls: CP-9, CP-10, SC-28, SC-5

## Context

SQLite is single-writer; enterprise needs multi-replica backend and HA.

Source: docs/enterprise/design.md section 5.

## Decision

Migrate to PostgreSQL managed by CloudNativePG (3 instances) and run the backend multi-replica. Details in ADR-0056 (Alembic, leader election, state in Postgres, CNPG-managed roles).

## Alternatives considered

Entries beyond those recorded in design.md are the obvious options, not documented discussion.

- Keep SQLite - no HA, no multi-replica.
- External managed DB - not available on-prem.

## Consequences

Positive:

- HA and scale.

Negative:

- Migration effort and operator dependence.

Follow-up work:

- Migration path and dual-backend support for homelab (phase 1).
