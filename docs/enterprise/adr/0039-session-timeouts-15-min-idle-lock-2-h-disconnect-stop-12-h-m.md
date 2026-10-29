# ADR-0039: Session timeouts: 15 min idle lock, 2 h disconnect stop, 12 h max

- Status: Proposed
- Date: 2026-10-28
- Decision ID: D39
- Related controls: AC-11, AC-12, SC-10

## Context

Device lock and session termination are required.

Source: docs/enterprise/design.md section 5.

## Decision

Lock the stream after 15 minutes idle; stop sessions disconnected 2 hours; enforce 12 hours maximum. The lock lives in the Styx gateway: it stops forwarding the stream and shows an overlay. Unlock is a fresh TLS handshake on login.<domain> with session resumption disabled, which proves card presence, not PIN entry (R02). (Builder call on mechanism.)

## Alternatives considered

Entries beyond those recorded in design.md are the obvious options, not documented discussion.

- Longer idle - weaker AC-11.
- No max duration - stale sessions.
- In-desktop lock screen - inside the user's own session, bypassable.

## Consequences

Positive:

- Clear AC-11/AC-12 mapping.
- Lock is enforced outside the desktop.

Negative:

- Unlock does not prove PIN entry (R02).
- Needs the Selkies lock-overlay patch (ADR-0058) and a gateway change.

Follow-up work:

- Implement gateway lock and overlay hook in phase 4.
