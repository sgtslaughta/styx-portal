# ADR-0046: Enterprise UX standard

- Status: Proposed
- Date: 2026-10-28
- Decision ID: D46
- Related controls: AT-2, SA-8, AU-2, AC-6

## Context

The target is a Citrix Workspace/AVD-like experience that is accessible.

Source: docs/enterprise/design.md section 5.

## Decision

Provide a home with My desktops, My services and announcements; desktops in their own tab with slim toolbar. Launch target is as low as achievable (owner: lower is better) — goal p50 ≤ 5 s, ceiling p95 < 10 s: images pre-pulled on all workers and home/profile mounted at pod start; per-image warm pools are dropped from v1 (optional later: per-user scheduled pre-warm). Also: light/dark design system with branding; self-service for quota, files, profiles and sessions; status banner and notifications; role-gated admin console; Section 508/WCAG 2.1 AA.

## Alternatives considered

Entries beyond those recorded in design.md are the obvious options, not documented discussion.

- Minimal UI - does not meet experience bar.
- Third-party portal - license/integration.

## Consequences

Positive:

- Polished user experience; accessible by design.

Negative:

- Large frontend scope.
- Launch is slower than a warm-pool design; accepted by the owner.

Follow-up work:

- Image pre-pull mechanism and launch-time instrumentation in phase 5.
