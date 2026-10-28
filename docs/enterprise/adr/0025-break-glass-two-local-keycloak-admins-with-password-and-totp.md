# ADR-0025: Break-glass: two local Keycloak admins with password and TOTP

- Status: Proposed
- Date: 2026-10-28
- Decision ID: D25
- Related controls: AC-2, IA-2, IA-5, AU-6, AC-2(2)

## Context

If CAC login or the IdP fails, administrators still need a way in. Passwords are otherwise excluded.

Source: docs/enterprise/design.md section 5.

## Decision

Provision two local Keycloak admin accounts (username, password, TOTP), credentials escrowed in OpenBao. Any use alerts ops and the security officer.

## Alternatives considered

Entries beyond those recorded in design.md are the obvious options, not documented discussion.

- No break-glass - risk of lockout.
- Shared admin account - weak accountability.

## Consequences

Positive:

- Recovery path with alerting.

Negative:

- Contradicts the CAC-only rule by design; exception must be documented.
- Escrow in OpenBao creates a dependency on OpenBao unseal.

Follow-up work:

- Offline copy of break-glass procedure; test annually (phase 2).
