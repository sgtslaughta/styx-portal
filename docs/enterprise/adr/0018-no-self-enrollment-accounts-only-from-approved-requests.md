# ADR-0018: No self-enrollment; accounts only from approved requests

- Status: Proposed
- Date: 2026-10-28
- Decision ID: D18
- Related controls: AC-2, IA-4, IA-12

## Context

Anyone obtaining an account without an approved request is an anti-goal. A valid CAC alone must not create an account.

Source: docs/enterprise/design.md section 5.

## Decision

Create accounts only from an approved request delivered by webhook (D19) or an admin CSV import. A CAC alone never creates an account.

## Alternatives considered

Entries beyond those recorded in design.md are the obvious options, not documented discussion.

- Just-in-time provisioning on first CAC login - violates the anti-goal.
- Manual admin creation only - slower, error-prone.

## Consequences

Positive:

- Every account traces to an approval.

Negative:

- Provisioning pipeline becomes critical.
- Onboarding latency depends on approvers.

Follow-up work:

- CSV import controls and audit in phase 2.
