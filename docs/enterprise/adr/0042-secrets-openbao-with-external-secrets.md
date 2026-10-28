# ADR-0042: Secrets: OpenBao with External Secrets

- Status: Proposed
- Date: 2026-10-28
- Decision ID: D42
- Related controls: SC-12, SC-13, SC-28, IA-5, SC-17

## Context

Dynamic DB credentials, app secrets, PKI, backup keys and break-glass escrow need a secrets manager without license ambiguity.

Source: docs/enterprise/design.md section 5.

## Decision

Use OpenBao for dynamic DB credentials, internal PKI, backup keys and break-glass escrow; deliver app secrets with External Secrets; split the Shamir unseal across 3 people.

## Alternatives considered

Entries beyond those recorded in design.md are the obvious options, not documented discussion.

- HashiCorp Vault - BSL license ambiguity.
- Kubernetes secrets alone - no rotation/PKI.

## Consequences

Positive:

- Open-source with MPL license; central key management.

Negative:

- Unseal procedure depends on 3 people (availability risk).
- Project maturity relative to Vault.

Follow-up work:

- Auto-unseal and rotation policy in phase 1.
