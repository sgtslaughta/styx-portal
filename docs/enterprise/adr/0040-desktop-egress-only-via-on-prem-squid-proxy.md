# ADR-0040: Desktop egress only via on-prem Squid proxy

- Status: Proposed
- Date: 2026-10-28
- Decision ID: D40
- Related controls: SC-7, SC-7(5), AU-2, AU-12, AC-4

## Context

Desktop internet traffic must be controlled and logged.

Source: docs/enterprise/design.md section 5.

## Decision

Permit desktop egress only through on-prem Squid with URL logs to Elastic; default-allow internet minus a blocklist; LAN only to approved services; allowlist mode per group.

## Alternatives considered

Entries beyond those recorded in design.md are the obvious options, not documented discussion.

- Direct NAT egress - no URL logging.
- Default-deny everywhere - heavy operational burden.

## Consequences

Positive:

- Visibility into outbound traffic.

Negative:

- Default-allow weakens exfiltration posture (see design inconsistencies).
- TLS interception question undecided.

Follow-up work:

- Blocklist source and TLS policy in phase 3.
