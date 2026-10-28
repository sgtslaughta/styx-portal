# ADR-0022: Offboarding: three independent off-switches

- Status: Proposed
- Date: 2026-10-28
- Decision ID: D22
- Related controls: AC-2, AC-2(3), PS-4, PS-5

## Context

Stale accounts are a major risk; no single mechanism should be relied on.

Source: docs/enterprise/design.md section 5.

## Decision

Provide a 'Remove access' flow that disables the account and kills sessions immediately; auto-disable at end date; disable after 35 days of inactivity; delete after a 90-day review.

## Alternatives considered

Entries beyond those recorded in design.md are the obvious options, not documented discussion.

- Manual-only offboarding - unreliable.
- Delete immediately - loses audit and data-handoff window.

## Consequences

Positive:

- Redundant triggers reduce orphaned accounts.

Negative:

- Inactivity disable may lock out legitimate infrequent users.
- Meaning of the '90-day review' start point is not fully specified.

Follow-up work:

- Specify review trigger and data disposition in phase 2.
