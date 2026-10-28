# ADR-0005: Prefer low/no-cost open-source components; paid items require an ADR

- Status: Proposed
- Date: 2026-10-28
- Decision ID: D05
- Related controls: SA-4, SA-9, SR-3

## Context

The owner's guiding rule is low to no cost; per-user license creep is an anti-goal.

Source: docs/enterprise/design.md section 5.

## Decision

Choose open-source, self-hosted components with no per-user fees by default. Any paid component needs its own ADR approving the exception. Accepted costs: Power Automate premium HTTP connector (D19), CUI offsite backup bucket (~$20-50/month, D37), Windows code-signing certificate plus Apple developer program (~$400/year, D41). Everything else is free.

## Alternatives considered

Entries beyond those recorded in design.md are the obvious options, not documented discussion.

- No policy, case-by-case buying - allows license creep.
- Commercial-first for support - conflicts with owner rule.

## Consequences

Positive:

- Predictable cost; exceptions are visible and reviewed.
- Reduces vendor lock-in.
- Owner has approved the listed costs.

Negative:

- Support is self-provided; small team carries more operational burden.
- License terms (e.g. BSL) need review for each component.

Follow-up work:

- Maintain a component/license register (phase 1).
