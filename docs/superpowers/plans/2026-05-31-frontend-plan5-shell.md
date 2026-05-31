# Frontend Rework — Plan 5: Shell (Header & TabNav)

> Small final plan. Implemented inline by the controller (changes are trivial). NO test runner — verify `npm run build`.

**Goal:** Denser header with tooltip status chips (using the Tooltip primitive); tighten TabNav. No behavior change.

## Task 1: header.tsx — tooltip status chips + density
- Replace the plain `N running · N stopped` text with small pill chips (running/paused/stopped/error), each a `Tooltip` with a descriptive label and a `statusMeta`-aligned dot color (success/warning/muted-foreground/destructive). Chips hide when count is 0.
- Reduce vertical padding (`py-3` → `py-2.5`) and title size for density. Keep the existing ThemeToggle unchanged.

## Task 2: tab-nav.tsx — tighten
- Reduce tab padding `py-2.5` → `py-2`. Keep semantic active/inactive styling.

## Verification
- `npm run build` passes; header chips show tooltips on hover; theme toggle works; tabs switch.
