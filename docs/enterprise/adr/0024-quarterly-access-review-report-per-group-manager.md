# ADR-0024: Quarterly access-review report per group manager

- Status: Proposed
- Date: 2026-10-28
- Decision ID: D24
- Related controls: AC-2, AC-2(3), AC-6

## Context

Periodic recertification of access is required for Moderate systems.

Source: docs/enterprise/design.md section 5.

## Decision

Generate a quarterly access-review report per group manager in the admin console, with certify and revoke actions and a CSV export. Admin CSV import must reference an approval record. (Builder call on format.)

## Alternatives considered

Entries beyond those recorded in design.md are the obvious options, not documented discussion.

- Annual review - too infrequent.
- Manual spreadsheets - error-prone.

## Consequences

Positive:

- Evidence of recertification with actions recorded.

Negative:

- Group managers must act on reports.

Follow-up work:

- Sign-off workflow and report content in phase 2/5.
