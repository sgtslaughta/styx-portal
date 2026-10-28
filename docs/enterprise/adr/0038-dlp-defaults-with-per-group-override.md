# ADR-0038: DLP defaults with per-group override

- Status: Proposed
- Date: 2026-10-28
- Decision ID: D38
- Related controls: AC-4, SC-7, AU-2, AU-12, MP-7

## Context

CUI must not leave through unlogged channels.

Source: docs/enterprise/design.md section 5.

## Decision

Allow clipboard text both ways; allow file upload in; disable download out and local printing; apply user+time watermark; log all transfers and clipboard events. Groups may override.

## Alternatives considered

Entries beyond those recorded in design.md are the obvious options, not documented discussion.

- Block clipboard entirely - usability cost.
- No logging of clipboard - violates anti-goal.

## Consequences

Positive:

- Controls and evidence for CUI handling.

Negative:

- Clipboard text both ways remains an exfiltration path, mitigated by logging.
- Logging clipboard content volume and privacy not specified.

Follow-up work:

- Event schema and enforcement points in phase 4.
