# ADR-0041: Smart-card passthrough via own open-source helper (phase 4)

- Status: Proposed
- Date: 2026-10-28
- Decision ID: D41
- Related controls: IA-2(12), SA-8, SA-11, SC-12

## Context

Browsers cannot reach card readers; commercial options carry licenses.

Source: docs/enterprise/design.md section 5.

## Decision

Build an own open-source helper (vpcd/virtualsmartcard-based), signed (Windows code-signing certificate, Apple developer program) and MDM-pushed, Windows first then macOS. It relays PC/SC only to the user's own session, authenticates with its own CAC mTLS plus a per-session one-time token, enforces an APDU allowlist, allows signing only with user interaction, and has its own threat model. Delivered in phase 4 because pilots need the card inside the desktop.

## Alternatives considered

Entries beyond those recorded in design.md are the obvious options, not documented discussion.

- Commercial passthrough - license fees.
- No passthrough - blocks in-desktop CAC use.

## Consequences

Positive:

- No license fees; control of implementation.

Negative:

- Custom security-critical code to maintain and assess.
- On the critical path for Pilot 25.
- Signing certificates are a recurring cost (ADR-0005).

Follow-up work:

- Threat model and signing process in phase 4.
