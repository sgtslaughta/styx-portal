# ADR-0039: Session timeouts: 15 min idle lock, 2 h disconnect stop, 12 h max

- Status: Proposed
- Date: 2026-10-28
- Decision ID: D39
- Related controls: AC-11, AC-12, SC-10

## Context

Device lock and session termination are required.

Source: docs/enterprise/design.md section 5.

## Decision

Lock the stream after 15 minutes idle with re-authentication by CAC PIN; stop sessions disconnected 2 hours; enforce 12 hours maximum.

## Alternatives considered

Entries beyond those recorded in design.md are the obvious options, not documented discussion.

- Longer idle - weaker AC-11.
- No max duration - stale sessions.

## Consequences

Positive:

- Clear AC-11/AC-12 mapping.

Negative:

- CAC PIN re-auth requires card access in the browser while smart-card passthrough is only phase 6.
- Lock mechanism inside Selkies is open.

Follow-up work:

- Decide lock-screen mechanism in phase 4.
