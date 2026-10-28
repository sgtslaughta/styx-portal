# ADR-0007: Kubernetes distribution: RKE2 with Cilium CNI

- Status: Proposed
- Date: 2026-10-28
- Decision ID: D07
- Related controls: CM-6, CM-7, SC-7, AC-4, SI-2

## Context

The cluster must be enterprise-hardened and free. The homelab already runs k3s.

Source: docs/enterprise/design.md section 5.

## Decision

Use RKE2 with Cilium as CNI for the enterprise profile; homelab remains k3s.

## Alternatives considered

Entries beyond those recorded in design.md are the obvious options, not documented discussion.

- k3s in enterprise - lighter but less hardening focus.
- Upstream kubeadm - more assembly work for a small team.
- OpenShift/Tanzu - licensing cost.

## Consequences

Positive:

- Hardened distribution at no cost.
- Cilium network policy supports microsegmentation and egress control.

Negative:

- Two distributions to track (see D03).
- Cilium expertise needed.

Follow-up work:

- Define default-deny network policy baseline in phase 1.
