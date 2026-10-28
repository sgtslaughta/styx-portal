# ADR-0016: Card-to-account key is EDIPI; username first.last, immutable

- Status: Proposed
- Date: 2026-10-28
- Decision ID: D16
- Related controls: IA-4, IA-5, AU-3

## Context

Audit records need readable identities and a stable key tying card to account.

Source: docs/enterprise/design.md section 5.

## Decision

Use EDIPI as the hidden attribute linking card to account. Visible username is first.last (digit appended on collision), display name 'Last, First M.', and the username never changes.

## Alternatives considered

Entries beyond those recorded in design.md are the obvious options, not documented discussion.

- Use email or UPN as key - mutable and not on the card.
- Use certificate subject DN - changes on reissue.

## Consequences

Positive:

- Stable identity across card reissue; readable audit logs.

Negative:

- EDIPI is sensitive and must be protected as hidden data.
- Name changes leave stale usernames.

Follow-up work:

- Exact EDIPI extraction/match config in phase 2.
