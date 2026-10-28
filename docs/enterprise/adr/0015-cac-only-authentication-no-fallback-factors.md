# ADR-0015: CAC-only authentication; no fallback factors

- Status: Proposed
- Date: 2026-10-28
- Decision ID: D15
- Related controls: IA-2, IA-2(12), IA-5(2), IA-8

## Context

Phishing-resistant authentication and a simple policy are priorities. A named anti-goal is passwords as a standing login method.

Source: docs/enterprise/design.md section 5.

## Decision

Authenticate users with CAC only. No FIDO2, TOTP or password fallback. Only break-glass accounts (D25) are excepted.

## Alternatives considered

Entries beyond those recorded in design.md are the obvious options, not documented discussion.

- FIDO2/TOTP fallback - weakens policy and adds support paths.
- Password fallback - named anti-goal.

## Consequences

Positive:

- Phishing-resistant; simplest policy to audit.
- Satisfies PIV acceptance.

Negative:

- Lost/expired card means no access until reissued.
- Requires card readers on managed clients.

Follow-up work:

- Document help-desk process for lost cards; exact Keycloak X.509 flow in phase 2.
