# Frontend Rework — Plan 2: Instances

> **For agentic workers:** Execute task-by-task. Frontend has NO test runner — verify each task with `cd /home/user/code/remote-access/frontend && npm run lint` (tsc --noEmit), and `npm run build` at the end. Commit per task. Preserve ALL existing behavior unless a task says to change it.

**Goal:** Refactor the Instances tab to consume the Plan 1 primitives (ActionBar, status.ts, Drawer, CHART_COLORS), apply the restrained-minimal aesthetic, decompose the mega-files, and remove all native `confirm()` calls + hardcoded status colors.

**Primitives available (from Plan 1):**
- `@/components/common/action-bar` → `<ActionBar instance={inst} size="sm"|"default" showConnect className />` — renders status-correct lifecycle buttons; reversible actions fire immediately (no confirm); destroy opens a type-to-confirm dialog internally.
- `@/components/common/confirm-dialog` → `<ConfirmDialog open onOpenChange title description confirmLabel variant="destructive" confirmPhrase onConfirm />`.
- `@/components/common/search-sort-bar` → `<SearchSortBar query onQueryChange placeholder sortOptions sortBy onSortChange>{children}</SearchSortBar>`.
- `@/components/ui/drawer` → `Drawer, DrawerTrigger, DrawerContent, DrawerHeader, DrawerBody, DrawerFooter, DrawerTitle, DrawerDescription` (right side, ~40% width).
- `@/lib/status` → `statusMeta(status)` → `{ label, textClass, dotClass, icon, pulse, group }`; `RUNNING_STATUSES`, `TRANSITION_STATUSES`, `isRunning`, `isTransitioning`.
- `@/lib/chart` → `CHART_COLORS.cpu`, `CHART_COLORS.memory` (CSS var strings).
- `@/lib/motion` → `fadeSlideIn`, `hoverLift`, `spring`, `listStagger`.

**Aesthetic rules:** No infinite glow/bounce/scale loops. Status conveyed by `statusMeta` dot/color + optional `animate-pulse` (already in status meta via `pulse`). Hover = subtle `hoverLift` (y:-2) only. Keep mount/exit `fadeSlideIn`. Replace all `bg-green-*/bg-amber-*/bg-red-*` action buttons and sparkline hex colors with primitives/tokens.

---

## Task 1: instance-card.tsx — consume ActionBar + status, decompose, calm motion

**Files:**
- Modify: `frontend/src/components/instances/instance-card.tsx` (311 → target < 200)
- Create: `frontend/src/components/instances/icon-viewport.tsx`

- [ ] **Step 1:** Extract the icon viewport (the `aspect-video` block: icon image/emoji + name overlay + status dot + dropdown menu) into a new `IconViewport` component in `icon-viewport.tsx`. Props: `{ instance: Instance; icon: string | null }`. Inside it:
  - Replace the per-state infinite framer-motion icon animation (the `animate={isRunning ? {scale/y/rotate loops}...}` and `drop-shadow rgba(...)` filter) with a **static** icon. Keep only: `grayscale opacity-20` when stopped/error, `opacity-40 saturate-50` when paused (use `statusMeta(status).group` to decide). No infinite loops, no rgba glow.
  - Replace the status dot block: use `statusMeta(instance.status)` → dot uses `dotClass` + `pulse && "animate-pulse"`. Remove the hardcoded `bg-green-500/bg-amber-500/...` ternary.
  - Keep the dropdown menu, but its lifecycle items now duplicate ActionBar — REMOVE the dropdown menu entirely (ActionBar in the card body replaces it). Keep the name overlay gradient (it's decorative, acceptable inline style) and the pulling `⏳` emoji case.

- [ ] **Step 2:** In `instance-card.tsx`, replace the entire bottom action-button block (the `isRunning ? ... : isPaused ? ... : isTransitioning ? ... : ...` ternary of colored buttons) with `<ActionBar instance={instance} size="sm" />`. Remove the now-unused handlers (`handleStart/Stop/Restart/Pause/Unpause/Destroy`, the `confirm()` call) and the now-unused mutation hooks. Keep `useInstanceStats` for the sparkline.

- [ ] **Step 3:** Replace the card's root infinite/whileHover animation: keep `motion.div` with `layout`, `variants={fadeSlideIn}` initial/animate/exit, `whileHover={hoverLift}`, `transition={spring}`. Remove the icon glow. Render `<IconViewport instance={instance} icon={icon} />` for the top, keep StatusBadge + uptime/idle + error box + sparkline + `<ActionBar .../>`.

- [ ] **Step 4:** Sparkline series colors: change `color: "#3b82f6"` → `CHART_COLORS.cpu`, `color: "#a855f7"` → `CHART_COLORS.memory`. Import `CHART_COLORS`.

- [ ] **Step 5:** Verify `npm run lint` passes. Commit:
```bash
git add src/components/instances/instance-card.tsx src/components/instances/icon-viewport.tsx
git commit -m "refactor(instances): card uses ActionBar+status, IconViewport extracted, calm motion"
```

---

## Task 2: instance-card-sm.tsx — ActionBar + tokens

**Files:**
- Modify: `frontend/src/components/instances/instance-card-sm.tsx`

- [ ] **Step 1:** Replace the action-button block (the hardcoded `text-amber-400 bg-amber-500/10` / `text-red-400` / `text-green-400` buttons) with `<ActionBar instance={instance} size="sm" />`. Remove now-unused lifecycle handlers, the `confirm()` destroy, and unused mutation hooks. Keep `useInstanceStats` + sparkline.
- [ ] **Step 2:** Status indicator → `statusMeta(instance.status)` for dot color/label. Remove hardcoded status colors.
- [ ] **Step 3:** Sparkline colors → `CHART_COLORS.cpu` / `CHART_COLORS.memory`.
- [ ] **Step 4:** Verify `npm run lint`. Commit:
```bash
git add src/components/instances/instance-card-sm.tsx
git commit -m "refactor(instances): card-sm uses ActionBar+status tokens"
```

---

## Task 3: instance-row.tsx — ActionBar + tokens

**Files:**
- Modify: `frontend/src/components/instances/instance-row.tsx`

- [ ] **Step 1:** Replace the row's action buttons (hardcoded `text-green-400 hover:bg-green-500/15` etc.) with `<ActionBar instance={instance} size="sm" />`. Remove unused handlers/hooks and the `confirm()` destroy.
- [ ] **Step 2:** Status → `statusMeta`. Sparkline colors → `CHART_COLORS`.
- [ ] **Step 3:** Verify `npm run lint`. Commit:
```bash
git add src/components/instances/instance-row.tsx
git commit -m "refactor(instances): row uses ActionBar+status tokens"
```

---

## Task 4: instance-grid.tsx — SearchSortBar, ConfirmDialog bulk destroy, token bulk bar

**Files:**
- Modify: `frontend/src/components/instances/instance-grid.tsx` (335)

Preserve ALL existing behavior: view modes (compact/normal/large), search, filter cycle, sort cycle, select-all, per-item selection, bulk start/stop/pause/resume/destroy, empty/loading/error states.

- [ ] **Step 1:** Replace the inline search `<input>` (the `<div className="relative flex-1 max-w-xs">…<input/>` block) with `<SearchSortBar query={search} onQueryChange={setSearch} placeholder="Search instances…">` wrapping the existing filter/sort/view cycle buttons as its `children`. Keep the select-all button and the `processed.length/total` count next to it.
- [ ] **Step 2:** Bulk action bar: replace hardcoded `text-green-400 bg-green-500/10` / `text-amber-400` / `text-red-400` buttons with `<Button size="sm" variant="secondary">` for start/pause/resume/stop and `<Button size="sm" variant="ghost" className="text-destructive hover:text-destructive">` for destroy. Keep the same labels/counts and onClick handlers.
- [ ] **Step 3:** Replace `bulkDestroy`'s native `confirm()` (line ~128) with a `ConfirmDialog`. Add state `const [bulkConfirm, setBulkConfirm] = useState(false)`. The Destroy bulk button sets `setBulkConfirm(true)`. Render `<ConfirmDialog open={bulkConfirm} onOpenChange={setBulkConfirm} title={\`Destroy ${selected.size} instance(s)?\`} description="Containers will be removed. Named volumes are kept." confirmLabel="Destroy" variant="destructive" confirmPhrase="destroy" onConfirm={runBulkDestroy} />` where `runBulkDestroy` is the old body (forEach destroy + toast + clearSelection). (Use the literal phrase `destroy` since multiple names can't be typed.)
- [ ] **Step 4:** Replace the loading skeleton infinite opacity pulse with Tailwind `animate-pulse` divs (no framer infinite). Keep AnimatePresence for grid items but ensure item motion uses calm presets (items themselves animate via their card components).
- [ ] **Step 5:** Verify `npm run lint`. Commit:
```bash
git add src/components/instances/instance-grid.tsx
git commit -m "refactor(instances): grid SearchSortBar + ConfirmDialog bulk destroy + token bulk bar"
```

---

## Task 5: instance-detail.tsx — convert to side Drawer, decompose tabs, ConfirmDialog destroy

**Files:**
- Modify: `frontend/src/components/instances/instance-detail.tsx` (411 → target < 220)
- Create: `frontend/src/components/instances/detail-tabs.tsx` (GeneralTab, SessionTab)

Preserve ALL form behavior: name/env/session editing, `dirty` tracking, the save flow including running-instance restart (`showRestartConfirm` → stop→update→start), `doSave` change-detection logic, toasts.

- [ ] **Step 1:** Extract the General tab body and the Session tab body into `detail-tabs.tsx` as `GeneralTab` and `SessionTab` components, each taking the relevant value + setter props (e.g. `GeneralTab`: `{ instance, name, setName, markDirty }`; `SessionTab`: `{ idleTimeout, setIdleTimeout, gracePeriod, setGracePeriod, timeoutAction, setTimeoutAction, neverTimeout, setNeverTimeout, markDirty }`). The Environment tab keeps using `<EnvEditor>` inline. Keep all existing JSX/classes inside the extracted tabs (just relocate).
- [ ] **Step 2:** Convert the outer `Dialog`/`DialogContent` to `Drawer`/`DrawerContent` (right side). Use `DrawerHeader` (title + StatusBadge), `DrawerBody` (the status grid + Tabs), `DrawerFooter` (the actions). Keep `open={!!instance} onOpenChange={(v)=>!v && onClose()}`. The 90vw dialog becomes the drawer's default ~40% width — no explicit width override needed.
- [ ] **Step 3:** Replace the footer lifecycle buttons (Connect/Pause/Stop/Resume/Start) with `<ActionBar instance={instance} />` — BUT keep the Save button flow separate: when `dirty`, show the Save button (existing `handleSave`/`doSave` logic + the `showRestartConfirm` warning box, which stays — it's a save-restart confirm, not a destroy). When not dirty, render `<ActionBar instance={instance} />`. Remove the separate Destroy `<Button variant="destructive">` and its `handleDestroy` + `confirm()` — ActionBar provides destroy with type-to-confirm. After ActionBar destroy succeeds the list refetches; also call `onClose()` — pass an `onDestroyed={onClose}` only if ActionBar supports it; it does NOT, so instead keep a small effect: when `instance` disappears from the query the drawer closes via parent. Simplest: leave `onClose` to the parent (App passes selectedInstance); no extra wiring needed. Remove `handleDestroy` and the destroy Button.
- [ ] **Step 4:** Keep the restart-confirm warning box but restyle from `border-yellow-500/50 bg-yellow-500/10 text-yellow-600` to tokens: `border-warning/50 bg-warning/10 text-warning`.
- [ ] **Step 5:** Verify `npm run lint`. Commit:
```bash
git add src/components/instances/instance-detail.tsx src/components/instances/detail-tabs.tsx
git commit -m "refactor(instances): detail as side Drawer, tabs decomposed, ActionBar + token restart box"
```

---

## Phase Verification

- [ ] **Step 1:** `npm run build` — must pass.
- [ ] **Step 2:** `grep -rnE "confirm\(|bg-(green|amber|red)-[0-9]|#[0-9a-fA-F]{6}|rgba\(" src/components/instances/` — expect NO matches for `confirm(`, and no hardcoded status colors / hex / rgba in instances components (sparkline series now use CHART_COLORS; the gradient overlay in icon-viewport may keep its inline `linear-gradient(rgba(0,0,0,…))` for the name scrim — that's the only allowed rgba). Report any remaining matches.
- [ ] **Step 3:** Manual smoke: `npm run dev` — open Instances, toggle the three views, search/filter/sort, select multiple → bulk destroy shows type-to-confirm dialog, open an instance → right-side drawer with tabs, edit a field → Save flow, destroy from drawer → type-to-confirm. Verify both themes.

## Notes for executor
- If removing mutation hooks from a card leaves an unused import, delete the import (tsc with the project config may not error on unused, but keep it clean).
- ActionBar already wires toasts + destroy confirm; do not double-wrap.
- Do not change `use-instances.ts`, `types.ts`, or the API client.
