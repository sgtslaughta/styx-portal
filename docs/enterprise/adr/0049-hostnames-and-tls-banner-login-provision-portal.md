# ADR-0049: Hostnames and TLS layout

- Status: Proposed
- Date: 2026-10-28
- Decision ID: D49
- Related controls: AC-8, SC-8, SC-23, IA-3

## Context

Client certificates must be requested only where needed so the AC-8 banner shows first and streams do not renegotiate.

Source: docs/enterprise/design.md section 5.

## Decision

Banner host: no client-cert request, shows the AC-8 banner first. login.<domain>: CAC mTLS, Keycloak. provision.<domain>: mTLS with the OpenBao CA, webhook only, GCC High IP allowlist. Portal/stream host: no client-cert request. Desktops are path-routed (/i/<sub>), so no wildcard cert. Server certificates come from an org/DoD-issued CA or free ACME as allowed. (Builder call.)

## Alternatives considered

Entries beyond those recorded in design.md are the obvious options, not documented discussion.

- Single host with optional client cert - browser cert prompts before the banner.
- Wildcard subdomain per desktop - needs wildcard cert.

## Consequences

Positive:

- Banner precedes any cert prompt.
- Small certificate set.

Negative:

- Several hostnames and redirects to keep consistent.

Follow-up work:

- Confirm certificate source with the org in phase 1.
