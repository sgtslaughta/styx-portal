# ADR-0045: Help-desk shadowing with consent

- Status: Proposed
- Date: 2026-10-28
- Decision ID: D45
- Related controls: AC-2, AC-6, AU-2, AC-17

## Context

Help desk needs to assist users while preserving privacy and accountability.

Source: docs/enterprise/design.md section 5.

## Decision

Require user consent to view, a second consent to control, a 'being viewed' banner, and log all shadowing.

## Alternatives considered

Entries beyond those recorded in design.md are the obvious options, not documented discussion.

- Silent admin viewing - privacy and accountability issues.
- No shadowing - reduces supportability.

## Consequences

Positive:

- Accountable support access.

Negative:

- Users may be unavailable to consent.

Follow-up work:

- Technical mechanism in phase 5.
