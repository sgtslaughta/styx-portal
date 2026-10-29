# ADR-0026: Admin roles: platform admin, help desk, auditor, group manager

- Status: Proposed
- Date: 2026-10-28
- Decision ID: D26
- Related controls: AC-2, AC-5, AC-6, AU-9

## Context

Administrative duties must be separated and least-privileged.

Source: docs/enterprise/design.md section 5.

## Decision

Define four roles: platform admin, help desk, auditor (read-only) and group manager. Admin roles are granted only in Keycloak by platform admins.

## Alternatives considered

Entries beyond those recorded in design.md are the obvious options, not documented discussion.

- Single admin role - violates separation of duties.
- Role grants inside Styx - splits authority across systems.

## Consequences

Positive:

- Clear AC-5 story; auditor independence.

Negative:

- Platform admins remain powerful; compensating monitoring needed.

Follow-up work:

- Role-permission matrix in phase 2.
