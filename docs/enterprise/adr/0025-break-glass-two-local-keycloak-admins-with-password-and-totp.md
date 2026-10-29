# ADR-0025: Break-glass: two local Keycloak admins with password and TOTP

- Status: Proposed
- Date: 2026-10-28
- Decision ID: D25
- Related controls: AC-2, IA-2, IA-5, AU-6, AC-2(2)

## Context

If CAC login or the IdP fails, administrators still need a way in. Passwords are otherwise excluded.

Source: docs/enterprise/design.md section 5.

## Decision

Provision two local Keycloak admin accounts (username, password, TOTP). Any use alerts ops and the security officer. The break-glass set is escrowed in OpenBao and also offline, sealed in the safe: offline RKE2 kubeconfig, OpenBao root/recovery, Ceph admin key, and the Styx emergency admin (D42).

## Alternatives considered

Entries beyond those recorded in design.md are the obvious options, not documented discussion.

- No break-glass - risk of lockout.
- Shared admin account - weak accountability.

## Consequences

Positive:

- Recovery path with alerting.

Negative:

- Contradicts the smart-card-only rule by design (R06).
- OpenBao escrow alone would depend on unseal; the offline copy removes that dependency.
- Offline safe needs custody procedure and periodic checks.

Follow-up work:

- Offline copy of break-glass procedure; test annually (phase 2).
