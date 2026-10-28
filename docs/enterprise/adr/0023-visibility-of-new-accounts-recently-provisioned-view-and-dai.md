# ADR-0023: Visibility of new accounts: Recently provisioned view and daily digest

- Status: Proposed
- Date: 2026-10-28
- Decision ID: D23
- Related controls: AC-2(4), AU-6, AU-12

## Context

A human should see every new account quickly to catch fraudulent provisioning.

Source: docs/enterprise/design.md section 5.

## Decision

Show new accounts in an admin 'Recently provisioned' view, send a daily digest to the security officer, and offer one-click suspend.

## Alternatives considered

Entries beyond those recorded in design.md are the obvious options, not documented discussion.

- Rely on logs only - not actively reviewed.
- Approval-time review only - misses pipeline compromise.

## Consequences

Positive:

- Compensating control for webhook compromise within a day.

Negative:

- Alert fatigue if digest is large; depends on security officer attention.

Follow-up work:

- Digest format and escalation in phase 2.
