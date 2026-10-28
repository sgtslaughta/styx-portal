# ADR-0017: Revocation: OCSP on every login, cached CRL fallback

- Status: Proposed
- Date: 2026-10-28
- Decision ID: D17
- Related controls: IA-5(2), SC-17, IA-2(12)

## Context

DoD PKI practice relies on revocation checking for certificate-based login.

Source: docs/enterprise/design.md section 5.

## Decision

Check OCSP at every login and fall back to a cached CRL when OCSP is unavailable.

## Alternatives considered

Entries beyond those recorded in design.md are the obvious options, not documented discussion.

- CRL only - staleness window.
- No revocation checking - unacceptable for CAC.

## Consequences

Positive:

- Timely revocation; resilient to OCSP outage.

Negative:

- Dependence on DoD OCSP reachability from the DMZ/Keycloak.
- Cached CRL fallback has a bounded staleness risk.

Follow-up work:

- Set CRL cache max-age and failure policy in phase 2.
