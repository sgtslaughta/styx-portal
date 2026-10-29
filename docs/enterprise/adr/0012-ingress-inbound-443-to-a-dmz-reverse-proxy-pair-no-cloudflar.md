# ADR-0012: Ingress: inbound 443 to a DMZ reverse-proxy pair; no Cloudflare or overlay

- Status: Proposed
- Date: 2026-10-28
- Decision ID: D12
- Related controls: SC-7, SC-8, SC-23, AC-17

## Context

CAC mutual TLS must terminate on-prem, and the stream path should be as short as possible with a documented boundary.

Source: docs/enterprise/design.md section 5.

## Decision

Expose inbound TCP 443 to a pair of DMZ HAProxy reverse proxies that terminate TLS (ADR-0050). No Cloudflare or overlay network.

## Alternatives considered

Entries beyond those recorded in design.md are the obvious options, not documented discussion.

- Cloudflare/Tunnel - terminates TLS off-prem, breaking on-prem CAC mTLS.
- Overlay/ZTNA - adds a component and path latency.

## Consequences

Positive:

- Documented, auditable boundary (SC-7).
- Shortest stream path.

Negative:

- Direct internet exposure demands strong DMZ hardening and DDoS handling.

Follow-up work:

- Define DMZ rules and the client-cert header format in phase 1/2.
