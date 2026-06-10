# UI Polish — Phase 2 Design

Date: 2026-06-10
Status: Approved (user, 2026-06-10)
Scope: Phase 2 of 3 (Phase 1 security hardening merged; Phase 3 = onboarding/diagnostics).
Stack: React 19, TypeScript, framer-motion, Radix UI, Tailwind v4, token-based theming.

## Goal

Production-grade polish across every authenticated touchpoint: professional, refined,
accessible, beginner-friendly without losing power-user depth. Full Phase 2 backlog.

## Decisions (user-approved)

- Full Phase 2 scope (all groups below).
- Login brand panel gets a **light-theme variant** that preserves the existing WebGL
  ripple (built on the uncommitted `RippleCanvas.tsx` / `LoginBrandPanel.tsx` work).

## Current-state notes (verified, not assumed)

- `LoginPage.tsx` already maps SSO `?error=` codes to friendly copy. Login-form errors
  still show raw `e.message`; password field has no show/hide, no submit loading, no `aria-invalid`.
- `api/client.ts` already redirects to `/login` on 401 for non-`/auth/` paths. No
  *proactive* expiry warning or silent-refresh-with-prompt exists.
- Provider test endpoint returns structured `{ok, checks:[{label,ok,detail}]}` — the
  "raw JSON" audit note is stale; we render checks as a readable list, not pretty-print JSON.
- `api.keepalive(id)` and `getInstanceStatus(id)` (returns `idle_seconds`) exist — idle
  countdown + keepalive button is wired to real endpoints.

## Group A — Auth form polish

Files: `pages/LoginPage.tsx`, `pages/SetupWizard.tsx`, `pages/AcceptInvitePage.tsx`,
`components/ui/input.tsx` (extend), new `components/ui/password-input.tsx`.

- `PasswordInput`: wraps `Input` with an eye/eye-off toggle (lucide), `aria-label`
  "Show/Hide password", `aria-pressed`. Used in all three auth pages + provider-dialog secret.
- Submit buttons: `isSubmitting` state → disabled + spinner + "Signing in…/Creating…"
  text during the async call. Prevents double-submit.
- Inline validation: set `aria-invalid` on the offending input when an error is shown;
  error text wired via `aria-describedby`. Login error maps known backend messages
  ("Invalid credentials" → "Email or password is incorrect").
- SetupWizard already shows password strength; add the same `PasswordInput` + submit
  loading. Keep zxcvbn meter.
- SSO error block: add a "Try again" affordance that clears the `?error=` query param.

## Group B — Session resilience

Files: `auth/AuthContext.tsx` (+ provider), `api/client.ts`, new
`components/auth/SessionExpiryDialog.tsx`, `components/instances/instance-detail-pane.tsx`
(or instance card), `hooks/use-instances.ts`.

- **Proactive expiry warning:** access token TTL is 15 min. A timer in AuthProvider
  (reset on activity / successful request) fires a warning dialog ~2 min before expiry:
  "Your session is about to expire" + **"Stay signed in"** (calls `POST /api/auth/refresh`,
  resets timer) + "Sign out". If ignored and the token lapses, the existing 401→/login
  path catches it. Implementation: track last-activity timestamp; lightweight, no polling
  of server. Respects the fact that any successful API call already silently refreshes via
  the cookie — so the dialog is the *fallback* for an idle tab.
- **401 toast:** when `client.ts` redirects on 401 mid-action, set a `?expired=1` param and
  show a one-time toast on the login page ("Your session expired — please sign in again")
  rather than a silent bounce.
- **Idle countdown + keepalive:** for a running instance with a finite `idle_timeout`,
  show remaining idle time (from `getInstanceStatus.idle_seconds` + template idle window)
  and a **"Keep awake"** button calling `api.keepalive(id)`. Only render when the instance
  has a timeout (not `never_timeout`).

## Group C — Dashboard & error states

Files: `components/instances/instance-grid.tsx`, `instance-card.tsx`,
`components/instances/action-bar.tsx` (bulk actions).

- **Retry button** beside "Backend unavailable — retrying…" → manual `refetch()`.
- **Bulk-action loading:** disable bulk buttons + spinner while mutations run; prevent
  re-click. Per-instance optimistic "working" state.
- **Truncation:** instance name `truncate` + `title`; `error_message` `line-clamp-3` +
  tooltip for full text; toast messages capped (~140 chars) with full error to console.
- **Empty-state CTA:** detail-pane placeholder gets an actionable line ("Select an
  instance, or launch a new one from the Template Gallery").

## Group D — Settings & provider dialog

Files: `components/system/provider-dialog.tsx`, `components/system/users-panel.tsx`.

- **Collapsible sections** in provider-dialog: Basic / Advanced (endpoints, scopes) /
  Role mapping / Self-service — using Radix Accordion or `<details>`. Save button pinned
  in footer (already partially done in Phase-1 SSO work — verify, keep).
- **Readable test result:** render `checks[]` as a pass/fail list with icons + the
  `detail` string; big green/red summary banner from `ok`. (Not pretty-printed JSON.)
- **Role-mapping copy:** plain-English helper — "If a user's groups claim contains
  `<admin group>`, make them an admin." Surface the new `auto_promote_admins` toggle
  (Phase-1 backend field) with a one-line explanation.
- **Icon upload:** show preview immediately on select; validate size client-side before
  upload; clear field + inline error on oversize.
- **Invite URL:** present the generated invite link in a highlighted, copyable box with
  its expiry stated prominently.
- **Jargon:** expand "IdP" → "identity provider (SSO)" on first use / tooltip.

## Group E — Accessibility

Files: `lib/motion.ts` (centralize), framer-motion call sites, icon-only buttons, modals.

- **Reduced motion:** a shared `useReducedMotion()`-aware variants helper in `lib/motion.ts`;
  apply to instance-card/grid/action-bar entrance + the bulk action bar slide. WebGL ripple
  already respects it.
- **aria-labels** on all icon-only buttons (refresh, theme toggle, row actions, select-all).
- **Focus management:** Radix Dialog handles focus trap; set `initialFocus` to the first
  field in LaunchModal + provider-dialog; confirm Esc/overlay close work.
- **Status not by color alone:** ensure every status badge keeps a text label.

## Group F — Light mode

Files: `globals.css` (or theme tokens), `components/auth/LoginBrandPanel.tsx`,
`components/auth/RippleCanvas.tsx`.

- **Brand panel light variant:** light-theme gradient/colorway so a light-mode user
  doesn't get a dark slab next to a light form. Ripple colors adapt to theme (read the
  same CSS custom properties the panel uses). Driven by the existing theme class, not a
  separate toggle.
- **Card contrast:** raise `--card-border-color` saturation and/or card shadow in light
  mode so cards separate from the background.
- **Chart/sparkline colors:** verify contrast in light mode; adjust `lib/chart.ts` palette
  if washed out.

## Group G — Copy pass

Cross-cutting, folded into the groups above: friendly error mapping (Group A/C), empty-state
CTAs (Group C), jargon expansion (Group D), consistent button verbs ("Save" / "Save changes"
/ "Launch"). No separate task — applied where each string lives.

## Non-goals (Phase 2)

- Backend changes (Phase 2 is frontend-only except reading existing endpoints).
- Diagnostics endpoint / Health page, setup-wizard config validation, Docker pull progress,
  docs split (all Phase 3).
- Virtual scrolling / pagination for 1000+ instances (YAGNI until a user hits it).

## Testing

Frontend has no formal test runner wired beyond `tsc`. Verification per group:
- `npx tsc --noEmit` clean after every group.
- Manual visual check in the running app (Phase 3 adds real e2e). Component-level: render
  the changed page in both themes, exercise keyboard nav + reduced-motion (OS setting),
  confirm loading/error/empty states.
- Each group ships as its own commit; build (`npm run build`) must pass.

## Risks

- **Session timer correctness** — must reset on real activity and not fight the cookie's
  silent refresh; keep it a pure fallback for idle tabs, no aggressive polling.
- **Brand-panel light variant vs in-progress ripple work** — build on the uncommitted
  files; coordinate so the ripple's color source is theme-aware, not hardcoded dark.
- **framer-motion reduced-motion** — verify variants actually short-circuit, not just
  shorten, when the OS flag is set.
