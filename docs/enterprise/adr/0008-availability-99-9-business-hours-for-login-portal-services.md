# ADR-0008: Availability: 99.9% business hours for login/portal/services

- Status: Proposed
- Date: 2026-10-28
- Decision ID: D08
- Related controls: CP-2, CP-10, SI-13

## Context

Containers cannot live-migrate. Ops staff are 2-3 people, business hours, best effort after hours.

Source: docs/enterprise/design.md section 5.

## Decision

Target 99.9% availability during business hours for login, portal and services. Running desktops may drop and reconnect after node loss.

## Alternatives considered

Entries beyond those recorded in design.md are the obvious options, not documented discussion.

- 99.9% for desktops - infeasible without live migration.
- 24x7 target - not supported by staffing.

## Consequences

Positive:

- Realistic, measurable target aligned with staffing.
- Drives HA for Keycloak, Postgres, Styx.

Negative:

- Users lose in-memory desktop state on node failure.
- Needs SLO measurement to demonstrate.

Follow-up work:

- SLO definitions and dashboards in phase 1 and D44.
