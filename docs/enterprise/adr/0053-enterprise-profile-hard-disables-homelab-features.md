# ADR-0053: Enterprise profile hard-disables homelab features

- Status: Proposed
- Date: 2026-10-28
- Decision ID: D53
- Related controls: CM-7, CM-6, IA-2, AC-3

## Context

One codebase (ADR-0003) must not leak homelab paths into the enterprise build.

Source: docs/enterprise/design.md section 5.

## Decision

The enterprise profile hard-disables password login, matrix-card 2FA, generic OIDC providers, workstation enrollment and Docker routers. A config test verifies it and a diagnostics endpoint lists the enabled features. (Builder call.)

## Alternatives considered

Entries beyond those recorded in design.md are the obvious options, not documented discussion.

- Rely on documentation - drift.
- Separate build - violates never-fork.

## Consequences

Positive:

- Least functionality is testable and assessable.

Negative:

- Profile flags add test matrix.

Follow-up work:

- Config test in CI in phase 1.
