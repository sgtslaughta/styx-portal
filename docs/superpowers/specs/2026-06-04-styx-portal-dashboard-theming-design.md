# Styx Portal — Full Dashboard Theming

**Date:** 2026-06-04
**Status:** Approved (brainstorm)

## Goal

Extend the branded Styx Portal aesthetic from the login/onboarding pages into the
main application (dashboard), as a **full surface redesign** in the "immersive depth"
direction (gradient/glass cards, blue glow, river brand motif).

## Decisions (locked)

- **Direction:** B — immersive depth (gradient cards, blue glow + shadow, richer chrome).
- **Header motion:** static river motif (no animation) — it's a tool people stare at all day.
- **Light mode:** matches the drama (gradient cards + blue tints + glow in light too, tuned for readability).
- **Reactivity:** rides on the existing `ThemeProvider` (root-level, live OS listener) — every
  surface flips light/dark live on all routes.

## Architecture — token-first, DRY

Do **not** hand-style each component. Extend the design system in
`frontend/src/styles/globals.css`:

1. **New CSS variables** (defined in BOTH `:root` and `.dark`):
   - `--surface-gradient` — page background wash
   - `--card-gradient` — instance/template/panel card background
   - `--card-border` — card border color (brand-tinted)
   - `--card-glow` — card box-shadow (depth + faint blue)
   - `--brand-accent` — sky-blue brand accent (glyph, highlights)
   - `--motif-color` — river current line color (low alpha)
   - `--header-gradient` — branded header band background

2. **Reusable utility classes:**
   - `.styx-app-bg` — page background using `--surface-gradient`
   - `.styx-header` — branded header band (`--header-gradient`)
   - `.styx-motif` — `::before` static diagonal river current (115° repeating-linear-gradient
     masked to fade), using `--motif-color`. NO animation.
   - `.styx-card` — `--card-gradient` bg + `--card-border` + `--card-glow` shadow

Components adopt these classes / tokens. One source of truth; no per-file palette drift.

### Palette (target values, refine during impl)

Dark mode (primary):
- `--surface-gradient: radial-gradient(120% 140% at 10% 0%, #0c1322 0%, #0a0e17 60%)`
- `--card-gradient: linear-gradient(160deg, #121d30, #0d1420)`
- `--card-border: #213050`; `--card-glow: 0 1px 0 rgba(90,150,255,.08) inset, 0 6px 18px -10px rgba(40,90,200,.5)`
- `--header-gradient: radial-gradient(120% 180% at 10% 50%, #0c1830 0%, #0a0f1a 60%)`
- `--brand-accent: #5b9bff`; `--motif-color: rgba(70,140,255,.06)`

Light mode (dramatic-but-readable):
- `--surface-gradient: radial-gradient(120% 140% at 10% 0%, #eef3fb 0%, #e7ecf4 60%)`
- `--card-gradient: linear-gradient(160deg, #ffffff, #eef3fb)`
- `--card-border: #d4def0`; `--card-glow: 0 1px 2px rgba(40,90,200,.06), 0 8px 20px -14px rgba(40,90,200,.35)`
- `--header-gradient: linear-gradient(90deg, #e9eff8, #eef3fb)`
- `--brand-accent: #2f6fe0`; `--motif-color: rgba(40,90,200,.05)`

These are starting values; tune for contrast during implementation. The river motif on the
header must never reduce text contrast below readable.

## Surfaces in scope (phased)

### Phase 1 — Foundation
- `globals.css`: add all tokens + utility classes above.
- `App.tsx`: apply `.styx-app-bg` to the page shell wrapper.

### Phase 2 — App chrome
- `components/layout/header.tsx`: `.styx-header` + `.styx-motif`; replace `Monitor` icon with
  `Waves` glyph in `--brand-accent`; `STYX PORTAL` wordmark (tracking); restyle `CountChip`
  status chips (pill + colored dot).
- `components/layout/tab-nav.tsx`: active tab = inset ring + tint pill (mockup B); inactive muted.

### Phase 3 — Instance surfaces
- `components/instances/`: `instance-card.tsx`, `instance-card-sm.tsx`, `instance-grid.tsx`,
  `instance-row.tsx`, `instance-thumbnail.tsx`, `instance-detail-pane.tsx` — adopt `.styx-card`,
  themed status pills, blue accents on primary actions.

### Phase 4 — Templates + System
- `components/templates/`: `template-grid.tsx` + template cards, `registry-browser.tsx` → `.styx-card`.
- `components/settings/settings-layout.tsx`, `components/system/metrics-*.tsx` panels,
  `components/common/stat-tile.tsx` → surfaces + accent.

Each phase is independently shippable (builds + renders correctly on its own).

## Out of scope

- shadcn UI primitives (`components/ui/*`) are NOT rewritten per-file; they inherit via tokens.
  Only touch a `ui/*` file if a token can't reach it.
- No new animation anywhere (static motif only).
- No layout/structure changes — this is visual theming, not re-layout. Card grids, tab
  structure, routes stay as-is.
- No backend changes.

## Verification

No frontend test harness exists. Per phase:
- `cd frontend && npx tsc --noEmit` → no new type errors.
- `cd frontend && npm run build` → succeeds.
- Manual visual check: each touched surface in light AND dark; confirm text contrast readable,
  motif subtle, cards consistent.

## Non-goals / risks

- Risk: light-mode "drama" hurting readability — mitigate by keeping gradients near-white and
  glow faint; verify contrast.
- Risk: token sprawl — keep to the variable set above; if a surface needs a one-off, prefer
  composing existing tokens over adding new ones.
