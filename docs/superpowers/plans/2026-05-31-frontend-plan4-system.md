# Frontend Rework — Plan 4: System / Metrics

> **For agentic workers:** READ each target file before editing it — this plan gives component-level directives, not line-exact code. NO test runner — verify each task with `cd /home/user/code/remote-access/frontend && npm run lint`, `npm run build` at end. Commit per task. PRESERVE all behavior (live polling, tabs, log tailing, session/image actions).

**Goal:** Make the System tab consistent with the new design system: tokenize all hardcoded amber/red/hex colors, route chart/sparkline colors through `CHART_COLORS`/`CHART_PALETTE`, adopt `StatTile`/`Gauge`/`DataTable` where they cleanly fit, and replace the remaining native `confirm()` (metrics-sessions) with `ConfirmDialog`. Calm the framer-motion entrances.

**Primitives:** `@/components/common/{stat-tile (StatTile, Gauge), data-table (DataTable, Column), confirm-dialog, action-bar}`, `@/lib/status` (statusMeta), `@/lib/chart` (CHART_COLORS, CHART_PALETTE), `@/lib/motion` (fadeSlideIn).

**Color token map (apply everywhere in this tab):**
- `text-amber-400` / `text-amber-*` → `text-warning`; `bg-amber-500/NN` → `bg-warning/NN`; `border-amber-500/NN` → `border-warning/NN`
- `text-red-400`/`text-red-300` → `text-destructive`; `bg-red-500/NN` → `bg-destructive/NN`; `border-red-500/NN` → `border-destructive/NN`
- Chart hex: `#34d399` (green) → `CHART_COLORS.cpu`-style usage is per-metric; map CPU→`var(--chart-1)`, memory/RAM→`var(--chart-2)`, network→`var(--chart-3)`, storage→`var(--chart-4)`. A red threshold color (`#ef4444`) for over-threshold may map to `var(--destructive)`.

---

## Task 1: metrics-overview.tsx — StatTile/Gauge + token alert colors

**Files:** Modify `frontend/src/components/system/metrics-overview.tsx` (~216)

- [ ] **Step 1:** Read the file. Identify the CPU/RAM "gauge cards" and the uptime stat and the alert box.
- [ ] **Step 2:** Replace the bespoke metric cards with `<StatTile icon={…} label value sub />` and, where a percentage bar is shown, `<Gauge value={pct} label color={var(--chart-N)} />`. Keep the exact values/labels/data sources. If a card's layout doesn't map cleanly to StatTile, leave its structure but tokenize its colors.
- [ ] **Step 3:** Tokenize all hardcoded amber/red per the color map (alert box `border-red-500/30 bg-red-500/5` → `border-destructive/30 bg-destructive/5`, amber alert → warning).
- [ ] **Step 4:** Verify `npm run lint`. Commit:
```bash
git add src/components/system/metrics-overview.tsx
git commit -m "refactor(system): overview uses StatTile/Gauge + token alert colors"
```

---

## Task 2: metrics-resources.tsx — chart colors via CHART tokens + Gauge

**Files:** Modify `frontend/src/components/system/metrics-resources.tsx` (~253)

- [ ] **Step 1:** Read the file. Find the hardcoded chart hex literals (`#34d399`, `#a78bfa`, `#60a5fa`, `#ef4444`) and any gauge/threshold logic.
- [ ] **Step 2:** Replace hex literals: CPU→`var(--chart-1)`, RAM/memory→`var(--chart-2)`, network/other→`var(--chart-3)`, storage→`var(--chart-4)`, over-threshold red→`var(--destructive)`. Import `CHART_COLORS` from `@/lib/chart` and prefer its named keys (`CHART_COLORS.cpu/.memory/.network/.storage`) where the metric is clear; use raw `var(--destructive)` for the threshold-exceeded color.
- [ ] **Step 3:** Where the file draws a simple percentage bar that matches `Gauge`, use `<Gauge value max label color />`. Keep custom SVG/line charts as-is (just swap colors). Calm any `repeat: Infinity` framer animation to a one-shot/none; keep live data updates.
- [ ] **Step 4:** Verify `npm run lint`. Commit:
```bash
git add src/components/system/metrics-resources.tsx
git commit -m "refactor(system): resources charts use CHART tokens, Gauge where it fits"
```

---

## Task 3: metrics-sessions.tsx — DataTable + ConfirmDialog destroy + token actions

**Files:** Modify `frontend/src/components/system/metrics-sessions.tsx` (~251)

- [ ] **Step 1:** Read the file. Identify the sessions table, the per-row action buttons (amber/red), the error box, and the native `confirm()` at ~line 172.
- [ ] **Step 2:** Convert the sessions table to `<DataTable columns={…} rows={sessions} rowKey={…} />` with columns for the existing fields (instance name, user, duration, idle, actions). The actions column renders the existing action buttons. Keep sorting if the table had it (DataTable supports `sortable`/`sortValue` per column — wire the columns that were sortable; if none were, omit). If the session object is a full `Instance`, you MAY render `<ActionBar instance={session} size="sm" />` in the actions column; otherwise keep the existing buttons but tokenize their colors.
- [ ] **Step 3:** Replace the native `confirm()` destroy with a `ConfirmDialog` (type-to-confirm on the instance name). Add `const [destroyTarget, setDestroyTarget] = useState<Session | null>(null)` (use the real type), the destroy button sets the target, and render one `<ConfirmDialog open={!!destroyTarget} onOpenChange={(v)=>!v && setDestroyTarget(null)} title=… confirmPhrase={destroyTarget?.name ?? ""} variant="destructive" confirmLabel="Destroy" onConfirm={() => runDestroy(destroyTarget)} />`.
- [ ] **Step 4:** Tokenize the error box and any remaining amber/red per the color map.
- [ ] **Step 5:** Verify `npm run lint`. Commit:
```bash
git add src/components/system/metrics-sessions.tsx
git commit -m "refactor(system): sessions DataTable + ConfirmDialog destroy + token colors"
```

---

## Task 4: metrics-logs.tsx — token warn/error highlight + calm motion

**Files:** Modify `frontend/src/components/system/metrics-logs.tsx` (~212)

- [ ] **Step 1:** Read the file. Find the warn/error log highlight classes (`bg-amber-500/5`, `bg-red-500/5`, `bg-amber-500/30 text-amber-200`) and the framer-motion entrance.
- [ ] **Step 2:** Tokenize: warn highlights → `bg-warning/10` / `text-warning`; error highlights → `bg-destructive/10` / `text-destructive`. Keep readable contrast.
- [ ] **Step 3:** Replace the motion entrance with `variants={fadeSlideIn}` (initial/animate) or a plain element if motion adds little; remove any `repeat: Infinity`. Preserve live-tail, search filter, autoscroll, instance selection.
- [ ] **Step 4:** Verify `npm run lint`. Commit:
```bash
git add src/components/system/metrics-logs.tsx
git commit -m "refactor(system): logs token warn/error highlight + calm motion"
```

---

## Task 5: image-manager.tsx — token colors + ConfirmDialog purge

**Files:** Modify `frontend/src/components/system/image-manager.tsx` (~141)

- [ ] **Step 1:** Read the file. It already uses a `confirmPurge` state modal — replace that bespoke confirm modal with the shared `<ConfirmDialog>` (type-to-confirm phrase `purge` since multiple images). Per-image delete: if it uses native `confirm()`, also route through ConfirmDialog (phrase = image name); if it deletes immediately, leave it (image delete is reversible by re-pull — acceptable, but a ConfirmDialog is nicer; implementer's call, keep simple).
- [ ] **Step 2:** Tokenize purge button `bg-red-500/20 text-red-400` → `bg-destructive/20 text-destructive` (or use `<Button variant="ghost" className="text-destructive">`), and warning box `border-amber-500/20 bg-amber-500/5` → `border-warning/20 bg-warning/5`.
- [ ] **Step 3:** Replace any `repeat: Infinity` skeleton with Tailwind `animate-pulse`.
- [ ] **Step 4:** Verify `npm run lint`. Commit:
```bash
git add src/components/system/image-manager.tsx
git commit -m "refactor(system): image-manager token colors + ConfirmDialog purge"
```

---

## Phase Verification

- [ ] **Step 1:** `npm run build` — must pass.
- [ ] **Step 2:** `grep -rnE "confirm\(|bg-(amber|red)-[0-9]|text-(amber|red)-[0-9]|#[0-9a-fA-F]{6}" src/components/system/` — expect NO native `confirm(`, no hardcoded amber/red, no hex chart colors (CHART_COLORS uses `var(--chart-N)` strings, not hex). Report any remaining matches.
- [ ] **Step 3:** Manual smoke: System tab → Overview gauges/alerts render in both themes; Resources charts render with themed colors + live updates; Sessions table sorts/acts, destroy shows type-to-confirm; Logs tail + warn/error highlight readable; Image manager purge shows type-to-confirm.

## Notes for executor
- Do NOT modify use-system.ts, use-images.ts, use-instances.ts, or the API client.
- If converting the sessions table to DataTable risks losing a behavior you can't cleanly preserve, keep the table markup but still tokenize colors and replace confirm() — report this as a DONE_WITH_CONCERNS deviation.
- Keep all live polling / refetch intervals untouched.
