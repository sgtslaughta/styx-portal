# ADR-0059: Notifications via portal and Matrix; SMTP optional

- Status: Proposed
- Date: 2026-10-28
- Decision ID: D59
- Related controls: AU-6, IR-4, SI-4

## Context

The org SMTP relay is unknown.

Source: docs/enterprise/design.md section 5.

## Decision

Notifications and alerts go to the portal and Matrix. An SMTP relay is optional configuration if one is provided later.

## Alternatives considered

Entries beyond those recorded in design.md are the obvious options, not documented discussion.

- Require SMTP - blocks on unknown org service.

## Consequences

Positive:

- No external dependency.

Negative:

- Matrix availability matters for alerting; portal is the fallback.

Follow-up work:

- Add SMTP config option in phase 5.
