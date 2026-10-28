# ADR-0034: Home quota 10 GB per user; 2 GB per-app profiles

- Status: Proposed
- Date: 2026-10-28
- Decision ID: D34
- Related controls: SC-5, SC-28, CM-12

## Context

Storage is limited and conservative defaults are preferred.

Source: docs/enterprise/design.md section 5.

## Decision

Give each user a 10 GB home (warn at 80%) mounted in every desktop, and 2 GB persistent profiles per app.

## Alternatives considered

Entries beyond those recorded in design.md are the obvious options, not documented discussion.

- Unlimited homes - exhausts capacity.
- Ephemeral-only desktops - loses user data.

## Consequences

Positive:

- Bounded storage growth.

Negative:

- Users with larger data needs must use OneDrive or request overrides.

Follow-up work:

- Self-service quota view in phase 5.
