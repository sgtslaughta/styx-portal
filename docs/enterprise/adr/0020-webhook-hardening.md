# ADR-0020: Webhook hardening

- Status: Proposed
- Date: 2026-10-28
- Decision ID: D20
- Related controls: AC-3, AC-17, IA-3, IA-5, SC-7, SC-8, SI-10, AU-2

## Context

The webhook is the only door into account creation and therefore a high-value target.

Source: docs/enterprise/design.md section 5.

## Decision

Require mTLS (OpenBao-issued client cert, rotated yearly) plus bearer token (90-day), GCC High IP allowlist at the DMZ for the provision host only, approval-ID check, approver validation, strict schema, idempotency, non-admin groups only, and audit of every call. Approver validation means Styx checks that the asserted approver is a known group manager; it cannot verify the M365 approval itself. The real control is the human review in D23 (R04).

## Alternatives considered

Entries beyond those recorded in design.md are the obvious options, not documented discussion.

- Bearer token alone - single factor on the only entry point.
- VPN to GCC High - not available per design.

## Consequences

Positive:

- Layered controls; limited blast radius (non-admin groups only).

Negative:

- Cert and token rotation operations.
- Dependence on stable GCC High IP ranges.
- A compromised flow could assert a valid manager; detected only by the D23 review.

Follow-up work:

- mTLS terminates on provision.<domain> at the DMZ proxy (ADR-0049, 0050); confirm in phase 2.
