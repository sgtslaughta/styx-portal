# Selkies Hub — Frontend Rework Design

**Date:** 2026-05-31
**Status:** Approved (design phase)
**Scope:** Full visual + structural rework of `frontend/src`. No backend changes, no new runtime dependencies.

## Goal

A polished, restrained-minimal, dense UI with a consistent reusable component layer. Custom confirmation dialogs (type-to-confirm for destructive actions; no native `confirm()`/`alert()`). Data surfaced through tooltips, popovers, and drawers. Master-detail layouts use 40/60 splits where they aid scanning.

## Current State (audit)

Stack: React 19, Tailwind 4, `radix-ui` umbrella (1.4.3), framer-motion 12, @tanstack/react-query 5, lucide-react, sonner. No chart library installed — metrics use custom SVG + framer-motion.

Strengths:
- Solid `components/ui/` primitives: Radix + CVA + semantic tokens, no hardcoded colors.
- Semantic token system in `globals.css` (oklch, light/dark, success/warning/idle/destructive).

Problems:
- ~75 hardcoded color literals (`bg-green-500`, `bg-amber-500`, `bg-red-500`, `rgba(...)`, hex) leak across `instance-*`, `metrics-*`, `image-manager`, `status-badge`.
- 7 native `confirm()` calls: instance-card:87, instance-card-sm:52, instance-row:52, instance-detail:154, instance-grid:128, template-card:18, metrics-sessions:172.
- Mega-files: launch-modal (490), instance-detail (411), instance-grid (335), instance-card (311).
- Heavy per-card animation (infinite glow/bounce loops) in instance-card.
- Duplicated lifecycle-button markup across card, card-sm, row, grid-bulk, detail, sessions.

## Architecture

Built in dependency order: a shared foundation, then reusable primitives, then per-area refactors that consume them. The four areas (Instances, Templates+Registry, System, Shell) can be refactored in parallel once the foundation and primitives land.

### Phase 1 — Design foundation

Single sources of truth for the values currently hardcoded everywhere.

- **`lib/status.ts`** — `STATUS_META: Record<InstanceStatus, { token, label, icon, dotClass, pulse }>` covering all 9 statuses. Every status color/label/icon decision flows from here. Consumed by status-badge, all instance cards/rows, sessions.
- **`lib/chart.ts`** — `CHART_PALETTE` array reading new CSS vars `--chart-1..4`. Replaces hex literals in sparkline and metrics charts. Themable via globals.css.
- **`lib/motion.ts`** — restrained motion presets: `fadeSlideIn` (mount), `hoverLift` (hover), `stateTransition` (status change). No infinite loops. "Running" indicated by a subtle accent ring/dot pulse, not a glowing bouncing icon.
- **`styles/globals.css`** — add `--chart-1..4` tokens (light + dark); tighten `--radius` for denser feel. Reuse existing semantic state tokens.

### Phase 2 — Reusable primitives

New files under `components/ui/` (Radix wrappers) and `components/common/` (composed domain primitives).

- **`ConfirmDialog`** — generic. Two modes: `simple` (Cancel / Confirm) and `type-to-confirm` (user types the resource name to enable Confirm). Used for irreversible actions only. Replaces all 7 native dialogs. **Destroy/purge use type-to-confirm. Reversible actions (stop/pause/restart/resume) fire immediately with no confirm** (undoable by restarting), surfacing result via toast.
- **`Tooltip`**, **`Popover`** — Radix wrappers added to `components/ui/` (available from the `radix-ui` umbrella; no new dep).
- **`Drawer`** — side-anchored Radix Dialog variant for master-detail panels.
- **`ActionBar`** — status-driven instance lifecycle controls (start/stop/pause/resume/restart/destroy). Takes an `Instance` + size variant; renders the correct buttons for the status. Single implementation consumed by card, card-sm, row, grid bulk actions, detail, and sessions. Wires ConfirmDialog for destroy.
- **`StatTile`** / **`Gauge`** — compact metric display tiles and radial/bar gauges for metrics tabs.
- **`DataTable`** — compact sortable table shell for instance rows, sessions, images.
- **`SearchSortBar`** — shared search + sort + filter control bar (instance-grid, registry-browser, sessions, logs).
- **`Sparkline`** — kept; refactored to draw from `CHART_PALETTE`, hex literals removed.

### Phase 3 — Per-area refactor

**Instances**
- `status-badge`, `instance-card`, `instance-card-sm`, `instance-row` consume `status.ts` + `ActionBar` + `Sparkline`.
- Decompose `instance-card` (311) → `IconViewport` + `ActionBar` + `StatsRow`.
- `instance-grid` (335) → extract `SearchSortBar`; keep view modes; bulk actions via `ActionBar`.
- `instance-detail` (411) → side **`Drawer`** (right-anchored, ~40% width) with split tab subcomponents: `StatusTab`, `EnvVarsTab`, `SessionConfigTab`. 40/60 master-detail against the list.
- All destroy actions → `ConfirmDialog` type-to-confirm.

**Templates + Registry**
- `template-card` aligned to the new card style; delete → `ConfirmDialog`.
- `launch-modal` (490) → decompose into `TemplateTab`, `ResourcesTab`, `AdvancedTab` + shared form-field components. Stays a Dialog (or Drawer if it reads better).
- `registry-browser` → `SearchSortBar` + 40/60 detail Drawer/Popover exposing changelog, env vars, ports.

**System / Metrics**
- `metrics-overview`, `metrics-resources`, `metrics-sessions`, `metrics-logs`, `image-manager` consume `StatTile`/`Gauge`/`DataTable`/`status.ts`/`CHART_PALETTE`.
- Replace `confirm()` in `metrics-sessions` and `image-manager` purge with `ConfirmDialog`.

**Shell**
- Header denser; instance counts become tooltip chips. Theme toggle stays (use existing `use-theme.ts`).
- TabNav tightened.

### Phase 4 — Polish & discipline

- Every component file targets < 300 lines (hard ceiling 500). Mega-files decomposed per above.
- Consistent spacing, radius, and motion across all tabs.

## Data Flow

No changes to data flow. Hooks (`use-instances`, `use-templates`, `use-registry`, `use-system`, `use-images`, `use-gpu`, `use-theme`) and the react-query layer are untouched. The rework is presentational and structural within the component tree. `ActionBar` calls the same mutation hooks the inline buttons call today.

## Error Handling

- Mutation errors continue to surface via `sonner` toasts (existing pattern).
- `ConfirmDialog` guards destructive mutations; on confirm it fires the mutation and shows success/error toast.
- Instance `error` status rendered via `status.ts` styling + existing error_message box, restyled with tokens.

## Testing / Verification

- `npm run build` (`tsc -b && vite build`) must pass with zero type errors.
- `npm run lint` (`tsc --noEmit`) must pass.
- Manual smoke after each area: load tab, toggle theme (light/dark/system), trigger a confirm flow, verify no native dialogs, verify sparklines/charts render in both themes.
- No new runtime dependencies added (verify `package.json` unchanged except possibly devDeps).

## Out of Scope

- Any backend or API change.
- Undo-toast pattern (requires backend support) — explicitly not chosen; type-to-confirm used instead.
- New chart or UI component libraries — custom SVG sparkline retained.
- Unrelated refactoring outside the presentational layer.

## Open Items / Risks

- `radix-ui` umbrella must export Tooltip/Popover/Dialog-as-drawer — verify at start of Phase 2; fall back to existing Dialog primitive if a sub-component is missing.
- Decomposing `launch-modal` and `instance-detail` carries the most regression risk (complex local form state) — refactor structurally without changing field behavior; verify each form submits identically.
