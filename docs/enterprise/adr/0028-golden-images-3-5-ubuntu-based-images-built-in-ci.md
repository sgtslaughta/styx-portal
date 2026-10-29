# ADR-0028: Golden images: 3-5 Ubuntu-based images built in CI

- Status: Proposed
- Date: 2026-10-28
- Decision ID: D28
- Related controls: CM-2, CM-3, CM-6, SA-10

## Context

Desktops must be consistent, patched and small in number. Upstream federal GitLab is the org's CI with on-prem runners available.

Source: docs/enterprise/design.md section 5.

## Decision

Maintain 3-5 Ubuntu-based golden images (base-office, developer, browser-only, GPU later) built in CI on upstream federal GitLab with on-prem runners.

Images are designed around M365 GCC High web apps (Outlook, Teams, Office, OneDrive) used from the in-desktop browser (owner-confirmed workflow); local office suites only where web apps fall short.

## Alternatives considered

Entries beyond those recorded in design.md are the obvious options, not documented discussion.

- Many per-team images - patching burden.
- Build on workstation by hand - not reproducible.

## Consequences

Positive:

- Owned, reproducible, small set.

Negative:

- CI dependence on an external (upstream) GitLab.
- Image content decisions per audience still to be made.

Follow-up work:

- Image bill of materials in phase 3.
