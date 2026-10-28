# ADR-0014: Keycloak as identity provider and user directory; no Active Directory

- Status: Proposed
- Date: 2026-10-28
- Decision ID: D14
- Related controls: IA-2, IA-4, IA-5, AC-2

## Context

The organization has no Active Directory. The IdP must handle X.509/CAC authentication.

Source: docs/enterprise/design.md section 5.

## Decision

Run Keycloak (two replicas) as IdP and the sole user directory.

## Alternatives considered

Entries beyond those recorded in design.md are the obvious options, not documented discussion.

- Active Directory - not available in the organization.
- Authentik/Zitadel - less mature X.509 support per design rationale.
- Managed IdP - cost and CUI hosting concerns.

## Consequences

Positive:

- Mature CAC support at no cost.
- Standard OIDC for Styx and services.

Negative:

- Keycloak becomes a critical, high-value component.
- Directory limited to Keycloak attributes.

Follow-up work:

- HA, backup and hardening of Keycloak in phase 2.
