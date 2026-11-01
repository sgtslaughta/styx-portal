# ADR-0051: Keycloak is authoritative; Styx admin client is limited

- Status: Proposed
- Date: 2026-10-28
- Decision ID: D51
- Related controls: AC-2, AC-3, AC-5, AC-6

## Context

Styx provisions users in Keycloak; a Styx compromise must not yield platform admin.

Source: docs/enterprise/design.md section 5.

## Decision

Keycloak is authoritative for users and groups. Styx mirrors groups from OIDC claims. Styx's Keycloak admin client is limited by fine-grained admin permissions to create, update and disable ordinary users and manage non-admin group membership; it cannot do role mapping. (Builder call.)

## Alternatives considered

Entries beyond those recorded in design.md are the obvious options, not documented discussion.

- Styx as source of groups - splits authority (ADR-0026).
- Full realm-admin client - large blast radius.

## Consequences

Positive:

- Limited blast radius.

Negative:

- Fine-grained admin permissions are fiddly to configure and test.

Follow-up work:

- Test that the client cannot map roles, in phase 2.
