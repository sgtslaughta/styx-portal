# ADR-0016: Card-to-account key is EDIPI (CAC) or card UUID (PIV/PIV-I); username first.last, immutable

- Status: Proposed
- Date: 2026-10-28
- Decision ID: D16
- Related controls: IA-4, IA-5, AU-3

## Context

Audit records need readable identities and a stable key tying card to account.

Source: docs/enterprise/design.md section 5.

## Decision

Link card to account with a hidden attribute: EDIPI for CAC, or the card UUID (urn:uuid in the SAN of the PIV Authentication certificate) for PIV and PIV-I. Binding happens at first login: an approved request (name, email, card type, EDIPI if CAC) is matched by the first card login whose certificate name/email matches it, which binds the card id; a mismatch is held for admin review. Card reissue is a help-desk rebind (logged). Visible username is first.last (digit appended on collision), display name 'Last, First M.', and the username never changes.

## Alternatives considered

Entries beyond those recorded in design.md are the obvious options, not documented discussion.

- Use email or UPN as key - mutable and not on the card.
- Use certificate subject DN - changes on reissue.
- EDIPI for all cards - PIV-I has no EDIPI.

## Consequences

Positive:

- Stable identity across card reissue; readable audit logs.
- Works for every accepted card type.

Negative:

- EDIPI and card UUID are sensitive and must be protected as hidden data.
- Name changes leave stale usernames.
- Rebind on reissue is a help-desk step that needs strong logging.

Follow-up work:

- Exact EDIPI/UUID extraction and match config in phase 2; admin review queue for mismatches.
