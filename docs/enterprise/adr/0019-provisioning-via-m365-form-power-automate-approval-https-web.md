# ADR-0019: Provisioning via M365 Form, Power Automate approval, HTTPS webhook

- Status: Proposed
- Date: 2026-10-28
- Decision ID: D19
- Related controls: AC-2, AC-2(1), IA-4

## Context

The organization uses M365 GCC High, but no M365 service accounts are available.

Source: docs/enterprise/design.md section 5.

## Decision

Users request access with an M365 Form; Power Automate runs approval and calls an HTTPS webhook (SCIM-shaped) into Styx, which provisions Keycloak. The premium HTTP connector is licensed (accepted cost, ADR-0005); the flow has two licensed named co-owners; cost recorded.

## Alternatives considered

Entries beyond those recorded in design.md are the obvious options, not documented discussion.

- Service-account-based Graph polling - no M365 service accounts available.
- Custom request portal - duplicates org tooling.

## Consequences

Positive:

- Uses org tooling; no extra license.

Negative:

- Power Automate is an external dependency and trust anchor.
- SCIM subset is not yet defined.
- Flow ownership and licensing must survive staff turnover (two co-owners).

Follow-up work:

- Define the SCIM subset and schema in phase 2.
