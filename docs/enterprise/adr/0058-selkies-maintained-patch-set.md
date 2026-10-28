# ADR-0058: Selkies maintained patch set

- Status: Proposed
- Date: 2026-10-28
- Decision ID: D58
- Related controls: SA-10, SI-7, AU-2, AC-11

## Context

Audit events, lock overlay and watermark need hooks in Selkies.

Source: docs/enterprise/design.md section 5.

## Decision

Maintain a patch set against Selkies (upstream where possible) for audit events, lock-overlay hook and encoder-burned watermark. The 'never fork' rule (ADR-0003) applies to Styx. (Builder call.)

## Alternatives considered

Entries beyond those recorded in design.md are the obvious options, not documented discussion.

- Do it all in the gateway - cannot burn watermark into the encoder.

## Consequences

Positive:

- Watermark cannot be removed client-side.

Negative:

- Patch rebase effort on each upstream release.

Follow-up work:

- Upstream patches first; track in phase 4.
