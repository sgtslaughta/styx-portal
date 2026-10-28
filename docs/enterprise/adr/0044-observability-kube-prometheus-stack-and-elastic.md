# ADR-0044: Observability: kube-prometheus-stack and Elastic

- Status: Proposed
- Date: 2026-10-28
- Decision ID: D44
- Related controls: AU-2, AU-3, AU-6, AU-11, SI-4, IR-4

## Context

Operations need metrics, SLOs and security logs; Elastic is the org SIEM.

Source: docs/enterprise/design.md section 5.

## Decision

Use kube-prometheus-stack for metrics and ship logs/audit to Elastic (90 days hot, 1 year archive). Provide SLO dashboards (login, launch time, stream latency, headroom). Stream latency is measured by a client-side RTT metric reported to Prometheus. Alerts and notifications go to the portal and Matrix; an SMTP relay is optional config if one is provided later (ADR-0059).

## Alternatives considered

Entries beyond those recorded in design.md are the obvious options, not documented discussion.

- Elastic only - no cluster metrics tooling.
- Commercial APM - cost.

## Consequences

Positive:

- Free, covers audit and operations.

Negative:

- Log volume cost (Squid hostnames, clipboard/file metadata events).
- Alert routing through Matrix depends on Matrix availability; the portal is the fallback.

Follow-up work:

- Alert and log retention details in phase 1.
