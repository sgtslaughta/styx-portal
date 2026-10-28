# ADR-0046: Enterprise UX standard

- Status: Proposed
- Date: 2026-10-28
- Decision ID: D46
- Related controls: AT-2, SA-8, AU-2, AC-6

## Context

The target is a Citrix Workspace/AVD-like experience that is accessible.

Source: docs/enterprise/design.md section 5.

## Decision

Provide a home with My desktops, My services and announcements; desktops in their own tab with slim toolbar; warm pools (~10% of peak, time-of-day) for ~3 s launch; light/dark design system with branding; self-service for quota, files, profiles and sessions; status banner and notifications; role-gated admin console; Section 508/WCAG 2.1 AA.

## Alternatives considered

Entries beyond those recorded in design.md are the obvious options, not documented discussion.

- Minimal UI - does not meet experience bar.
- Third-party portal - license/integration.

## Consequences

Positive:

- Polished user experience; accessible by design.

Negative:

- Large frontend scope; warm pools consume idle capacity.

Follow-up work:

- Warm-pool sizing algorithm in phase 5.
