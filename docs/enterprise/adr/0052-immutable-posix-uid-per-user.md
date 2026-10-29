# ADR-0052: Immutable POSIX UID per user

- Status: Proposed
- Date: 2026-10-28
- Decision ID: D52
- Related controls: AC-3, AC-2, IA-4

## Context

CephFS homes need stable numeric ownership across sessions and reissued cards.

Source: docs/enterprise/design.md section 5.

## Decision

Styx allocates an immutable POSIX UID per user, stored as a Keycloak attribute, used for CephFS home ownership. (Builder call.)

## Alternatives considered

Entries beyond those recorded in design.md are the obvious options, not documented discussion.

- Derive UID from username hash - collisions.
- Allocate in Styx DB only - lost on rebuild; Keycloak is authoritative.

## Consequences

Positive:

- Stable file ownership.

Negative:

- Allocator must never reuse a UID.

Follow-up work:

- Allocator and uniqueness test in phase 2/3.
