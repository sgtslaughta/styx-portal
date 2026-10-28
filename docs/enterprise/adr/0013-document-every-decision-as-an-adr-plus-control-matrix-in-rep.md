# ADR-0013: Document every decision as an ADR plus control matrix in repo

- Status: Proposed
- Date: 2026-10-28
- Decision ID: D13
- Related controls: CA-2, PL-2, SA-5

## Context

ATO evidence must be traceable to design decisions.

Source: docs/enterprise/design.md section 5.

## Decision

Maintain one ADR per decision (D01-D59) and a control matrix under docs/enterprise.

## Alternatives considered

Entries beyond those recorded in design.md are the obvious options, not documented discussion.

- Wiki-only documentation - not versioned with code.
- Ad-hoc notes - weak ATO evidence.

## Consequences

Positive:

- Auditable, reviewable history through git.
- Direct mapping of decisions to controls.

Negative:

- Documentation must be kept current as decisions change.

Follow-up work:

- Expand matrix statements each phase; supersede ADRs rather than editing silently.
