# ADR-0027: USG system-use banner before login

- Status: Proposed
- Date: 2026-10-28
- Decision ID: D27
- Related controls: AC-8

## Context

A standard system-use notification is required before authentication.

Source: docs/enterprise/design.md section 5.

## Decision

Display the USG banner on a banner host that does not request a client certificate, before the user is redirected to login.<domain> where the CAC mTLS happens (ADR-0049).

## Alternatives considered

Entries beyond those recorded in design.md are the obvious options, not documented discussion.

- Banner after login - does not meet notification-before-access.

## Consequences

Positive:

- Meets AC-8.

Negative:

- Banner text must be maintained as policy changes.

Follow-up work:

- Banner host and login flow in phase 2.
