# ADR-0050: DMZ proxy is an HAProxy pair forwarding the client cert

- Status: Proposed
- Date: 2026-10-28
- Decision ID: D50
- Related controls: SC-7, SC-8, SC-23, AC-17

## Context

The DMZ proxy terminates TLS; Keycloak must still see the client certificate to authenticate the card.

Source: docs/enterprise/design.md section 5.

## Decision

The DMZ proxy is a pair of HAProxy instances terminating TLS and forwarding the client certificate in a header format that Keycloak's x509 lookup SPI supports. Traefik runs in-cluster behind it. (Builder call; resolves the HAProxy-or-Traefik question in ADR-0012.)

## Alternatives considered

Entries beyond those recorded in design.md are the obvious options, not documented discussion.

- Traefik in the DMZ - less suited to header-based cert forwarding.
- TLS passthrough to Keycloak - loses DMZ inspection and rate limits.

## Consequences

Positive:

- Mature, well-understood DMZ component.

Negative:

- Header trust: only the proxy may set the cert header; Keycloak must reject it from elsewhere.

Follow-up work:

- Define header format, strip-and-set rules and network policy in phase 2.
