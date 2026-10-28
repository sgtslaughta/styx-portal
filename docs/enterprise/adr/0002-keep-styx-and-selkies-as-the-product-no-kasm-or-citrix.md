# ADR-0002: Keep Styx and Selkies as the product; no Kasm or Citrix

- Status: Proposed
- Date: 2026-10-28
- Decision ID: D02
- Related controls: SA-4, SA-9, SC-7

## Context

The enterprise needs containerized desktops with a polished experience. Commercial VDI products exist but carry per-user licensing; Styx already provides Selkies streaming plus workstation and service-proxy features.

Source: docs/enterprise/design.md section 5.

## Decision

Continue with Styx plus Selkies as the delivery stack. Do not adopt Kasm Workspaces or Citrix.

## Alternatives considered

Entries beyond those recorded in design.md are the obvious options, not documented discussion.

- Kasm Workspaces - not chosen; Selkies is judged better than VNC-based streaming and the license model conflicts with the no-fee rule.
- Citrix - per-user license fees; conflicts with the guiding rule and anti-goals.
- Plain VNC/noVNC - Selkies streaming quality is judged superior.

## Consequences

Positive:

- No per-user license fees.
- Reuses existing workstation/services features and owner knowledge.

Negative:

- Team owns Selkies/Styx defects and security patching itself.
- Upstream Selkies project risk (see SR family).

Follow-up work:

- Track upstream Selkies releases and licenses as part of supply-chain review (phase 3).
