# ADR-0040: Desktop egress via on-prem Squid with category blocking

- Status: Proposed
- Date: 2026-10-28
- Decision ID: D40
- Related controls: SC-7, SC-7(5), AU-2, AU-12, AC-4

## Context

Desktop internet traffic must be controlled and logged.

Source: docs/enterprise/design.md section 5.

## Decision

Internet is allowed by default with content/category blocking: Squid plus free category blocklists (for example UT1) with e2guardian-style filtering. File-sharing, webmail, paste sites and anonymizers are blocked. There is no SSL-bump (no TLS decryption), so filtering is by hostname/SNI and hostnames are logged to Elastic. LAN is reachable only for approved services. Cilium denies all non-proxy egress, including SSH and UDP/WebRTC. Allowlist mode per group remains. SC-7(5) is tailored (R01).

## Alternatives considered

Entries beyond those recorded in design.md are the obvious options, not documented discussion.

- Direct NAT egress - no logging.
- Default-deny everywhere - heavy operational burden.
- SSL-bump - decrypts CUI traffic and adds a high-value target.

## Consequences

Positive:

- Visibility into outbound hostnames; common exfiltration categories blocked.
- No TLS decryption keeps the proxy out of CUI content.

Negative:

- Uncategorized sites remain reachable; residual exfiltration risk accepted (R01).
- Hostname-only logs cannot show URLs or content.

Follow-up work:

- Blocklist update job and review cadence in phase 3.
