# ADR-0041: Smart-card passthrough via own open-source helper

- Status: Proposed
- Date: 2026-10-28
- Decision ID: D41
- Related controls: IA-2(12), SA-8, SA-11, SC-12

## Context

Browsers cannot reach card readers; commercial options carry licenses.

Source: docs/enterprise/design.md section 5.

## Decision

Build an own open-source helper (vpcd/virtualsmartcard-based), signed and MDM-pushed, Windows first then macOS. It relays PC/SC only to the user's own session over the authenticated connection and has its own threat model.

## Alternatives considered

Entries beyond those recorded in design.md are the obvious options, not documented discussion.

- Commercial passthrough - license fees.
- No passthrough - blocks in-desktop CAC use.

## Consequences

Positive:

- No license fees; control of implementation.

Negative:

- Custom security-critical code to maintain and assess.
- Delivered last (phase 6).

Follow-up work:

- Threat model and signing process in phase 6.
