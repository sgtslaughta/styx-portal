# Styx Portal — Rebrand + Login Redesign

**Date:** 2026-06-04
**Status:** Approved (brainstorm)

## Goal

Two changes:
1. Rebrand "Selkies Hub" → "Styx Portal" across all surfaces (user-facing + infra).
2. Redesign the login page: animated two-panel split, light/dark aware, sleek/modern.

User authorized stopping running deployments and deleting the existing DB, so the
rebrand needs **no migration code** — clean rename plus documented ops steps.

---

## Part 1 — Rebrand

### User-facing strings

| File | Change |
|------|--------|
| `frontend/index.html` | `<title>Selkies Hub` → `Styx Portal` |
| `frontend/src/components/layout/header.tsx` | wordmark `Selkies Hub` → `Styx Portal` |
| `frontend/src/pages/LoginPage.tsx` | covered by redesign (Part 2) |
| `frontend/src/pages/SetupWizard.tsx` | brand strings |
| `frontend/src/pages/AcceptInvitePage.tsx` | brand strings |
| `frontend/src/components/system/metrics-overview.tsx` | brand strings |
| `frontend/package.json` | `name: selkies-hub-frontend` → `styx-portal-frontend` |
| `README.md` | title + body references |

### Backend / infra

| File | Change |
|------|--------|
| `backend/app/config.py` | `DATABASE_URL` → `sqlite+aiosqlite:///./data/styx-portal.db`; `DOCKER_NETWORK` `selkies-hub` → `styx-portal` |
| `backend/app/main.py` | `FastAPI(title="Styx Portal")`; logger `getLogger("styx-portal")` |
| `backend/app/services/traefik_labels.py` | any `selkies-hub` literal |
| `backend/app/services/docker_manager.py` | any `selkies-hub` literal |
| `backend/app/services/screenshot.py` | any `selkies-hub` literal |
| `backend/app/routers/oauth.py` | any `selkies-hub` literal |
| `backend/tests/*` | update assertions referencing old network / title / db strings (`test_config.py`, `test_traefik_labels.py`, `test_docker_manager.py`) |

### Out of scope (keep "Selkies")

`selkies-desktop`, `linuxserver/baseimage-selkies`, and the Selkies framebuffer/streaming
references are the **upstream streaming technology**, not our brand. These stay.

### Ops steps (user runs, documented in README)

```bash
docker compose down
docker network rm selkies-hub        # old network
rm -f backend/data/selkies-hub.db    # old DB (fresh start authorized)
docker compose up -d                 # recreates styx-portal network + fresh DB
```

### Verification

- `grep -ri "selkies hub\|selkies-hub" --include=*.{ts,tsx,py,json,html,md}` returns
  only intentional upstream refs (none for our brand).
- Backend tests pass: `cd backend && .venv/bin/python -m pytest -v`
- ruff clean: `.venv/bin/python -m ruff check app/ tests/`
- Frontend builds: `cd frontend && npm run build`

---

## Part 2 — Login redesign

### Layout

- Full-height two-panel split. Left = brand panel, right = form panel.
- Responsive: below `md`, stacks to single column — brand panel collapses to a short
  header bar (logo + tagline one line), form fills the rest.

### Brand panel (always dark, both themes)

- Base: `radial-gradient(140% 120% at 15% 100%, #0a1426 0%, #070a12 45%, #05070d 100%)`
  — near-black with a **very subtle** dark-blue depth hint rising from bottom-left.
- Two animated "river current" layers (diagonal `repeating-linear-gradient` at 115°),
  masked to fade toward top-right:
  - Layer 1: 22px pitch, `rgba(70,140,255,.09)`, 14s linear drift.
  - Layer 2 (depth): 40px pitch, `rgba(40,90,200,.06)`, 26s linear drift.
  - Drift keyframe: `translate(0,0)` → `translate(-23px,-49px)`, infinite.
- Content: glyph `⟁` + `STYX PORTAL` wordmark (top); tagline "Cross over to your
  workspaces." + subtitle "Secure remote desktops, on demand." (bottom).
- `@media (prefers-reduced-motion: reduce)` → drift animation disabled (static lines).

### Form panel (theme-aware via existing `dark` class)

- Light: bg `#eef1f5`, fields white `#fff` / border `#d6dbe2`.
- Dark: bg `#0d1018`, fields `#161b25` / border `#28303d`.
- Order: "Sign in" heading + welcome sub → SSO provider button(s) → "or" divider →
  Email + Password fields → primary "Sign in" button → error box.
- Preserves ALL current behavior from `LoginPage.tsx`:
  - `api.login({username, password})` then `refresh()` then `nav("/")`
  - `api.oauthProviders()` load + `api.oauthStartUrl(name)` links
  - SSO error-code → message map (`not_authorized`, `email_unverified`, …)
- Note: backend auth field is `username`; the email-style input keeps `username` state
  binding (label may say "Email or username" to match the form factor without backend change).

### Theme integration

- Reuses `frontend/src/hooks/use-theme.ts` (light/dark/system, toggles `.dark` on
  `documentElement`). No new theme infra. Brand panel colors are hard-set (theme-independent);
  form panel uses theme-conditional classes / existing semantic tokens.

### Component structure (keep files < 500 lines)

- `LoginPage.tsx` — rewritten: owns state + submit + SSO logic + layout shell.
- `LoginBrandPanel.tsx` (new, small) — the animated dark panel, presentational only.
- Brand-panel CSS: project uses Tailwind. Animation `@keyframes` + the masked
  current-line layers go in the global stylesheet (`frontend/src/styles/globals.css`) under a
  small `.styx-brand` block; the TSX applies that class + Tailwind utilities. Keeps
  keyframes out of the TSX and reusable.

### Verification

- `npm run build` succeeds.
- Manual: light + dark + system themes render correctly; animation drifts; reduced-motion
  static; SSO buttons appear when providers configured; login + error paths work.

---

## Non-goals

- No backend auth logic changes.
- No DB migration (fresh DB authorized).
- No rename of upstream Selkies streaming tech.
- No new theme system.
