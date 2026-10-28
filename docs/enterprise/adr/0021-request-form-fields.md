# ADR-0021: Request form fields

- Status: Proposed
- Date: 2026-10-28
- Decision ID: D21
- Related controls: AC-2, IA-4, PS-4

## Context

The form must link a request to a card and support automatic offboarding.

Source: docs/enterprise/design.md section 5.

## Decision

Collect first name, last name, EDIPI, email, groups, approving manager and end date (required for contractors).

## Alternatives considered

Entries beyond those recorded in design.md are the obvious options, not documented discussion.

- Fewer fields without EDIPI - cannot link form to card.
- Optional end date for contractors - misses auto-offboarding.

## Consequences

Positive:

- EDIPI links form to card; end date drives auto-disable.

Negative:

- Form collects PII/EDIPI; Forms/Power Automate data handling must be CUI-appropriate.

Follow-up work:

- Retention and handling rules for form data to be decided in phase 2.
