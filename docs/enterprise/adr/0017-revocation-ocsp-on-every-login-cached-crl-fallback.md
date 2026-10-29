# ADR-0017: Revocation: OCSP on every login, cached CRL fallback

- Status: Proposed
- Date: 2026-10-28
- Decision ID: D17
- Related controls: IA-5(2), SC-17, IA-2(12)

## Context

DoD PKI practice relies on revocation checking for certificate-based login.

Source: docs/enterprise/design.md section 5.

## Decision

Check OCSP (per issuer) first and fall back to a local CRL mirror maintained by a cronjob and read by path in Keycloak. Alert on CRL age. (Builder call.)

## Alternatives considered

Entries beyond those recorded in design.md are the obvious options, not documented discussion.

- CRL only - staleness window.
- No revocation checking - unacceptable for smart cards.
- Per-login CRL download - slow and fragile.

## Consequences

Positive:

- Timely revocation; resilient to OCSP outage.

Negative:

- Dependence on DoD and federal OCSP reachability from Keycloak.
- CRL mirror has a bounded staleness risk, covered by the age alert.

Follow-up work:

- Set CRL max-age and failure policy in phase 2.
