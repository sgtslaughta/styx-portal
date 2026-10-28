# ADR-0003: One codebase, two deployment profiles; never fork

- Status: Proposed
- Date: 2026-10-28
- Decision ID: D03
- Related controls: CM-2, CM-3, SA-10, SI-2

## Context

Homelab (k3s) and enterprise (RKE2) both run Styx. Divergent code would double patching and testing effort.

Source: docs/enterprise/design.md section 5.

## Decision

Maintain a single codebase with two deployment profiles (homelab k3s, enterprise RKE2) selected by configuration. A fork of Styx is an explicit anti-goal.

## Alternatives considered

Entries beyond those recorded in design.md are the obvious options, not documented discussion.

- Long-lived enterprise fork - two patch streams; named anti-goal.
- Enterprise-only rewrite - discards working features and history.

## Consequences

Positive:

- One patch stream; fixes land once.
- Homelab acts as a pre-production proving ground.

Negative:

- Enterprise-specific features must be gated by profile and kept testable in both.
- Risk of homelab-oriented defaults leaking into enterprise.

Follow-up work:

- Define profile mechanism (values, feature flags) in phase 1.
