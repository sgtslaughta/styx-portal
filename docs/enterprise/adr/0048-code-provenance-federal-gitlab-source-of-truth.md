# ADR-0048: Code provenance: federal GitLab is the source of truth

- Status: Proposed
- Date: 2026-10-28
- Decision ID: D48
- Related controls: CM-3, SA-10, SR-4

## Context

The enterprise build must have a provenance story inside the ATO boundary.

Source: docs/enterprise/design.md section 5.

## Decision

The federal GitLab is the source of truth for the enterprise build. GitHub becomes a mirror. Merges that ship into the ATO boundary are approved on the federal GitLab. (New decision.)

## Alternatives considered

Entries beyond those recorded in design.md are the obvious options, not documented discussion.

- GitHub as source of truth - approvals outside the boundary.
- Two independent repos - drift.

## Consequences

Positive:

- Approvals and CI evidence sit inside the boundary.

Negative:

- Contributors need federal GitLab access; mirror lag.

Follow-up work:

- Set up mirroring and protected-branch approvals in phase 1.
