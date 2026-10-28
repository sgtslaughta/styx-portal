# ADR-0021: Request form fields

- Status: Proposed
- Date: 2026-10-28
- Decision ID: D21
- Related controls: AC-2, IA-4, PS-4

## Context

The form must link a request to a card and support automatic offboarding.

Source: docs/enterprise/design.md section 5.

## Decision

Collect first name, last name, email, card type (CAC/PIV/PIV-I), EDIPI (CAC only), groups, approving manager and end date (required for contractors).

## Alternatives considered

Entries beyond those recorded in design.md are the obvious options, not documented discussion.

- Fewer fields without card type - cannot bind PIV/PIV-I.
- Optional end date for contractors - misses auto-offboarding.

## Consequences

Positive:

- Request links to the card at first login (ADR-0016); end date drives auto-disable.

Negative:

- Form collects PII/EDIPI; Forms/Power Automate data handling must be CUI-appropriate.

Follow-up work:

- Retention and handling rules for form data to be decided in phase 2.
