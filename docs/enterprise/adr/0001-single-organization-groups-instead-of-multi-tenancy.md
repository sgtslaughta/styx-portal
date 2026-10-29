# ADR-0001: Single organization, groups instead of multi-tenancy

- Status: Proposed
- Date: 2026-10-28
- Decision ID: D01
- Related controls: AC-2, AC-3, AC-6

## Context

Styx serves one organization of roughly 200-500 staff with no resale plan. Multi-tenant isolation would require per-tenant data, network and admin boundaries throughout the stack.

Source: docs/enterprise/design.md section 5.

## Decision

Model one organization with groups/departments as the unit of policy and delegated administration. Multi-tenant isolation is a v1 non-goal.

## Alternatives considered

Entries beyond those recorded in design.md are the obvious options, not documented discussion.

- Multi-tenant (per-tenant realms, namespaces, databases) - roughly doubles design and test scope for no stated need.
- One deployment per department - multiplies operations load for a 2-3 person team.

## Consequences

Positive:

- Halves design and operational scope.
- Group-level policy (DLP, caps, egress) maps directly to AC-2/AC-3 evidence.

Negative:

- No hard isolation between groups beyond RBAC and policy; a tenant boundary cannot be claimed in the SSP.
- Retrofitting multi-tenancy later would be a significant change.

Follow-up work:

- Define the group model and group-manager scope in phase 2.
