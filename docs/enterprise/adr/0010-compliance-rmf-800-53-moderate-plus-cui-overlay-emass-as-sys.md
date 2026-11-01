# ADR-0010: Compliance: RMF, 800-53 Moderate plus CUI overlay, eMASS as system of record

- Status: Proposed
- Date: 2026-10-28
- Decision ID: D10
- Related controls: CA-1, CA-2, CA-6, PL-2, RA-3

## Context

Data is CUI and an ATO is required. Tracking is in eMASS.

Source: docs/enterprise/design.md section 5.

## Decision

Follow RMF with NIST 800-53 Rev 5 Moderate baseline plus the CUI overlay. eMASS is the system of record; repository documents are the source of content.

## Alternatives considered

Entries beyond those recorded in design.md are the obvious options, not documented discussion.

- Lower baseline - not valid for CUI.
- Documents only in eMASS - drift from engineering reality.

## Consequences

Positive:

- Single source of truth in repo, versioned with the code.
- Clear authorization target.

Negative:

- Documentation maintenance effort.
- eMASS sync is manual unless automated.

Follow-up work:

- Define eMASS export process; expand control matrix per phase.
