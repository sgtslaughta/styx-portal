# ADR-0037: Backup and DR: RPO 24 h, RTO 8 h; encrypted offsite copy

- Status: Proposed
- Date: 2026-10-28
- Decision ID: D37
- Related controls: CP-9, CP-10, CP-6, CP-7, SC-28

## Context

Moderate impact systems normally expect tested backup and recovery; the design has a single site.

Source: docs/enterprise/design.md section 5.

## Decision

Target RPO 24 h and RTO 8 h using CNPG backups, Velero and nightly home snapshots. Offsite copy is an encrypted export to a CUI-authorized cloud bucket (~$20-50/month, accepted), using CephFS snapshot-based incremental export. A full-site restore test is part of phase 1. No second site: CP-7 is a recorded exception (R03).

## Alternatives considered

Entries beyond those recorded in design.md are the obvious options, not documented discussion.

- Warm second site - cost and scope.
- Local-only backups - no site-loss protection.

## Consequences

Positive:

- Documented recovery objectives; offsite copy.

Negative:

- No alternate processing site (CP-7); risk acceptance R03.
- Recovery within 8 h is unproven until the phase 1 restore test.
- Recurring cloud cost.

Follow-up work:

- Full-site restore test (phase 1 exit); record CP-6/CP-7 in eMASS.
