# ADR-0043: Services: upstream GitLab link, Wiki.js, Matrix; OIDC to Keycloak

- Status: Proposed
- Date: 2026-10-28
- Decision ID: D43
- Related controls: IA-2, AC-3, SC-23

## Context

Users need org services available with SSO and no fees.

Source: docs/enterprise/design.md section 5.

## Decision

Link upstream federal GitLab, host Wiki.js and Matrix (Synapse plus Element), all via OIDC to Keycloak; non-OIDC apps sit behind Styx forwardAuth; Nextcloud dropped because OneDrive covers files.

## Alternatives considered

Entries beyond those recorded in design.md are the obvious options, not documented discussion.

- Nextcloud - dropped, OneDrive covers files.
- Host GitLab locally - non-goal.

## Consequences

Positive:

- Free with SSO.

Negative:

- Matrix and Wiki.js add operational surface and CUI considerations.

Follow-up work:

- Wiki.js and Matrix deployment in phase 5.
