# ADR-0029: Supply chain: nightly rebuild, scan, sign, SBOM, Harbor, Kyverno admission

- Status: Proposed
- Date: 2026-10-28
- Decision ID: D29
- Related controls: SR-3, SR-4, SI-2, SI-7, RA-5, CM-7, CM-14

## Context

Security updates must apply automatically and only trusted images may run.

Source: docs/enterprise/design.md section 5.

## Decision

Rebuild nightly, scan with Trivy, sign with cosign and produce an SBOM, store in Harbor, and have Kyverno admit only signed, allowlisted images.

## Alternatives considered

Entries beyond those recorded in design.md are the obvious options, not documented discussion.

- Manual patch cycles - slow.
- Registry without admission control - unsigned images could run.

## Consequences

Positive:

- Automatic secure updates; verifiable provenance.

Negative:

- Harbor and Kyverno become dependencies for launches.
- Scan false positives need triage.

Follow-up work:

- Define vulnerability SLAs (see D30) and key custody for cosign in phase 3.
