# Matrix-card second factor — design

## Why
The owner signs in from a locked-down shared public computer: no extensions, no hardware keys, no phone, and the Authentik domain (a.jmolabs.dev) is blocked there. Only g.jmolabs.dev is reachable, so username + password is the only path. A printed grid card ("matrix card") adds something-you-have that works with nothing but a keyboard.

## Goals (owner decisions)
- 5 columns (A–E) × 10 rows (1–10) = 50 cells; each login asks for **3 random cells**.
- The challenge is **fixed until answered correctly** (refresh/retry never re-rolls it; no cell shopping).
- **Required for password logins** for any user who has an active card. SSO (OAuth/OIDC) logins are not challenged.
- **Regenerate to revoke**: a new card replaces the old one.
- The UI shows the card as an **image the owner can download (PNG) and print**.
- Every card event is audited.

## Decided details
- Cell value: 3 characters from `ACDEFGHJKLMNPQRTUVWXY34679` (no 0/O, 1/I/L, 2/Z, 5/S, 8/B). Answers are case-insensitive, surrounding whitespace ignored. 3 cells ≈ 42 bits per challenge, plus existing lockout.
- Storage: card cells as JSON encrypted with the existing Fernet helper (`encrypt_secret`). The card is **shown once**, at generation; it cannot be re-displayed later (a stolen session cannot read it). Lost card → regenerate (while signed in) or admin reset.
- Enrollment is two-step so a card is never active before the owner has saved it: generate (requires current password) → pending card shown → owner answers one cell from it → card becomes active, replacing any previous card.
- Removing a card requires the current password. Admins can reset another user's card.
- Login: password OK + active card → no session yet. Server stores the challenge on the user, sets a short-lived (5 min) httponly `styx_mfa` cookie (signed JWT, type `mfa`, user id + token_version + card serial), returns `{"mfa_required": true, "challenge": [...]}`. `POST /api/auth/login/matrix` with the 3 answers completes the login.
- A wrong answer counts exactly like a wrong password (per-user lockout, per-IP fail tracker / ban) and audits `auth.matrix_failed`; the challenge stays the same.
- Card-verified sessions end when the browser closes: auth cookies are issued **without max-age** for matrix logins, and refreshes of that session family stay session-only.
- Card image is drawn client-side (canvas → PNG download; print view). No new backend dependency.

## Non-goals
TOTP/WebAuthn, card for SSO users, re-displaying a card, a global on/off switch.

## Left to the builder
Exact UI copy and layout, styling of the printed card.
