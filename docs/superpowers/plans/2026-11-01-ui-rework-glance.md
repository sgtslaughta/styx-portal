# UI rework "Glance" Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild the Styx frontend shell, home, New container flow, admin/settings, monitoring charts and login to the approved "Glance" design.

**Architecture:** Each phase is its own branch and PR (`feat/ui-glance-<n>-<slug>` off `main`) and ships working software on its own. The frontend stays React + Tailwind v4, with CSS tokens in `globals.css`. Charts are small hand-written SVG components with no chart library, ported from `docs/design/ui-rework-2026-11/charts.js`. The canvas effects (water, waves, dither, glyph beams) are framework-free TS modules mounted through one `useCanvasEffect` hook. On the backend: persisted hourly metric rollups, a stream-session log, and a few read-only stats endpoints.

**Tech Stack:** React 19, Vite, Tailwind v4, @tanstack/react-query, vitest + Testing Library, FastAPI + SQLModel (SQLite), pytest.

**Spec:** `docs/superpowers/specs/2026-11-01-ui-rework-glance-design.md`. The mockups in `docs/design/ui-rework-2026-11/` are the pixel reference: open `c5-glance.html` and `login-waves.html` in a browser and match them.

## Global Constraints

- Keep every file under 500 lines. Split by responsibility.
- Use semantic commits (`feat(frontend): …`, `feat(backend): …`) and semantic versioning. Each phase PR bumps the minor version.
- Frontend gate: `cd frontend && npm run build && npm test`. `npm run build` runs `tsc -b`, which is stricter than `tsc --noEmit`.
- Backend gate: `cd backend && .venv/bin/python -m pytest -q && .venv/bin/python -m ruff check app/ tests/`.
- Add no new npm or pip dependencies. The one allowed exception is the IBM Plex Mono font, as `@fontsource/ibm-plex-mono`.
- Gold is used only for: the active underline, section rules, the single primary action per view, focus rings and changed markers. Use the exact `--obol` and `--obol-edge` values from the spec.
- The chart palette slots are exactly the spec values, in the order s1 to s5, with s0 for "Others". Never generate extra hues.
- Copy rules: sentence case, no all-caps labels except the existing "STYX PORTAL" wordmark, and use the verbs given in the spec ("Resume", "Connect", "Save changes", "Discard").
- Every animation honours `prefers-reduced-motion` by rendering a still frame.
- Settings save only when Save is clicked. Never auto-save on change.

## Review Focus

1. **Many users or workstations (20+):** charts and the status rail must stay legible. Top-5 folding applies to every breakdown. *Test: `fold-top.test.ts` with 12 entities.*
2. **Fresh install, no history:** charts, sparklines and the Relay cost page show "No data yet", never NaN or empty axes. *Tests: `sparkline.test.tsx` and `line-chart.test.tsx` with `data=[]` and `data=[x]`.*
3. **Cloudflare token removed after setup:** the Relay cost nav item and Overview card disappear, and `/relay-cost` redirects to Overview. *Test in Task 12.*
4. **Leaving with unsaved settings:** switching admin page with dirty fields prompts "Discard N unsaved changes?". *Test in Task 8.*
5. **WebGL2 unavailable or canvas context lost (VMs, old GPUs):** water, waves and beams fall back to a static frame with no exceptions. *Test: `use-canvas-effect.test.tsx` with `getContext` returning null.*

---

## Phase 1: Theme foundation and header (`feat/ui-glance-1-theme`)

### Task 1: Gold tokens, chart palette, SectionHead

**Files:**
- Modify: `frontend/src/styles/globals.css` (add tokens under `:root` and `.dark`)
- Create: `frontend/src/components/common/section-head.tsx`
- Test: `frontend/src/components/common/__tests__/section-head.test.tsx`

**Interfaces:**
- Produces:
  - CSS vars `--obol`, `--obol-edge`, `--gold-text` (light `#86601F`, dark `#DDB869`), and `--s0`…`--s5`.
  - Utility classes `.btn-gold`, `.gold-rule`, `.gold-underline`.
  - `SectionHead({ title, note?, action?, as? = "h2" }): JSX`, which renders the heading, the `.gold-rule`, then `note` and `action`.

- [ ] **Step 1:** Test that `render(<SectionHead title="Desktops" note="3 machines" action={<button>New</button>} />)` puts the heading text, the note and the button in DOM order, and that the rule element has `aria-hidden="true"` and class `gold-rule`.
- [ ] **Step 2:** Run `cd frontend && npx vitest run src/components/common/__tests__/section-head.test.tsx`. Expected: FAIL (module not found).
- [ ] **Step 3:** Add the tokens and classes. Copy `.gold-rule` from `.sec-head .rule` and `.btn-gold` from `tokens.css` in the mockup. Implement `SectionHead`.
- [ ] **Step 4:** Rerun the test. Expected: PASS. Then run `npm run build`. Expected: OK.
- [ ] **Step 5:** `git commit -m "feat(frontend): gold tokens, chart palette, SectionHead"`

### Task 2: Shell header (gold diagonal lines, frosted labels, Home/Admin tabs)

**Files:**
- Modify: `frontend/src/components/layout/header.tsx`
- Delete: `frontend/src/components/layout/tab-nav.tsx` (its tabs move into the header)
- Modify: `frontend/src/App.tsx` (drop `TabNav` and the "templates" tab; tabs are now `home` and `admin`)
- Test: `frontend/src/components/layout/__tests__/header.test.tsx` (extend the existing file)

**Interfaces:**
- Produces: `Header({ activeTab: "home" | "admin", onTabChange })`. The Admin tab renders only when `user.role === "admin"`. The active tab has `aria-current="page"` and class `gold-underline`.

- [ ] **Step 1:** Tests:
  - (a) A non-admin user sees no "Admin" tab.
  - (b) Clicking "Admin" calls `onTabChange("admin")`.
  - (c) The header no longer renders the running/paused count chips (that information moves to the status rail).
- [ ] **Step 2:** Run the test. Expected: FAIL.
- [ ] **Step 3:** Implement. The header background uses `.styx-header` with two pseudo-layers copied from `.top::before/::after` in `c5-glance.html` (gold sheen masked into 115° lines, plus a shadow line offset 1px, with the mask-composite override placed *after* the `mask` shorthand). Add the frosted patch `::before` on the brand and tabs, from the "Frosted patch" rule in the mockup.
- [ ] **Step 4:** Run the tests and `npm run build`. Expected: PASS. Compare against `shots/hdr.png` with `npm run dev`.
- [ ] **Step 5:** `git commit -m "feat(frontend): gold river header with Home/Admin tabs"`

---

## Phase 2: Home (`feat/ui-glance-2-home`)

### Task 3: Canvas effect hook and water module

**Files:**
- Create: `frontend/src/lib/effects/water.ts` (TypeScript port of `docs/design/ui-rework-2026-11/ripple.js`)
- Create: `frontend/src/hooks/use-canvas-effect.ts`
- Test: `frontend/src/lib/effects/__tests__/water.test.ts`, `frontend/src/hooks/__tests__/use-canvas-effect.test.tsx`

**Interfaces:**
- Produces:
  - `createWater(canvas: HTMLCanvasElement, opts: WaterOptions): { drop(x, y, radius, strength): void; setSource(img: CanvasImageSource): void; destroy(): void }`. `WaterOptions` has the same keys as `ripple.js` (`mode`, `source`, `scale`, `damping`, `hoverRadius`, `hoverStrength`, `clickRadius`, `clickStrength`, `refract`, `light`, `tint`, `idleDrops`).
  - Pure helper `stepWave(cur: Float32Array, prev: Float32Array, w: number, h: number, damping: number): number`, which returns the peak absolute height.
  - `useCanvasEffect(ref, factory: (c) => { destroy(): void } | null, deps)`, which mounts on resize and destroys on unmount.

- [ ] **Step 1:** Tests:
  - `stepWave` on an 8×8 grid with one centre impulse of 1 returns a peak below 1 and spreads energy to its 4 neighbours.
  - After 400 steps at damping 0.97 the peak is below 0.004 (the stop threshold is an *absolute* peak, not scaled by grid size; this was a bug fixed in the mockup).
  - The hook test: when `getContext` returns null, `factory` returns null and nothing throws.
- [ ] **Step 2:** Run the tests. Expected: FAIL.
- [ ] **Step 3:** Port `ripple.js`. Image mode uses the WebGL2 shader; glass mode uses Canvas2D. If WebGL2 is missing, draw the static image. With reduced motion, `drop` does nothing.
- [ ] **Step 4:** Run the tests. Expected: PASS.
- [ ] **Step 5:** `git commit -m "feat(frontend): water ripple effect module + canvas hook"`

### Task 4: GlassButton and the home sections

**Files:**
- Create: `frontend/src/components/ui/glass-button.tsx`
- Create: `frontend/src/components/home/recent-strip.tsx`, `desktop-tiles.tsx`, `container-rows.tsx`, `home-page.tsx`
- Modify: `frontend/src/components/home/apps-grid.tsx` (dock style, red dot for needs-setup when admin)
- Delete: `frontend/src/components/home/home-tabs.tsx`, `frontend/src/components/instances/instance-workspace.tsx`. Move the detail-pane features into each row's "⋯" menu.
- Create: `frontend/src/lib/recents.ts`
- Tests: `frontend/src/components/home/__tests__/home-page.test.tsx`, `frontend/src/lib/__tests__/recents.test.ts`

**Interfaces:**
- Consumes: `createWater` and `useCanvasEffect` (Task 3), `SectionHead` (Task 1).
- Produces:
  - `GlassButton({ children, onClick, tone?: "light" | "teal" })`.
  - `HomePage({ onNewContainer })`.
  - `recentItems(instances, workstations, opened: Record<string, number>, n = 3): RecentItem[]`, where `RecentItem` is `{ kind: "desktop" | "container", id, name, status, thumbUrl, action: "Resume" | "Connect" | "Start" }`. `opened` is localStorage `styxOpened` (id mapped to ms).

- [ ] **Step 1:** Tests:
  - `recentItems` returns the 3 most recently opened items, newest first. An item the user is currently connected to always sorts first. Offline workstations are excluded.
  - `HomePage` renders the headings Recent, Desktops, Apps and Containers in that order.
  - The "New container" button sits inside the Containers heading.
  - A plain user sees no "Needs setup" dot.
- [ ] **Step 2:** Run the tests. Expected: FAIL.
- [ ] **Step 3:** Implement to match `c5-glance.html` (`.recent`, `.tile`, `.dock`, `.crow`). The glass button is always visible on recents; on tiles and rows it shows on hover, and always under `@media (hover: none)`.
- [ ] **Step 4:** Run the tests and `npm run build`. Expected: PASS.
- [ ] **Step 5:** `git commit -m "feat(frontend): Glance home: recent, desktops, apps, containers"`

### Task 5: Status rail (admin, pinned, collapsible)

**Files:**
- Create: `frontend/src/components/layout/status-rail.tsx`
- Modify: `frontend/src/App.tsx` (mount for admins; pad the content by the rail width)
- Test: `frontend/src/components/layout/__tests__/status-rail.test.tsx`

**Interfaces:**
- Consumes: the existing `api.getSystemMetrics()` and the active-sessions hook from `use-system.ts`.
- Produces: `StatusRail({ forceCollapsed?: boolean })`. The collapsed state persists in localStorage `styxRail` (`"open"` or `"closed"`).

- [ ] **Step 1:** Tests:
  - The toggle flips `aria-expanded` and writes `styxRail`.
  - `forceCollapsed` shows the collapsed strip with CPU %, the live count and a "to check" badge.
  - It is not rendered for non-admins.
- [ ] **Step 2:** Run the tests. Expected: FAIL.
- [ ] **Step 3:** Implement: rail width 320px, collapsed width 56px, `position: fixed` under the header.
- [ ] **Step 4:** Run the tests. Expected: PASS.
- [ ] **Step 5:** `git commit -m "feat(frontend): admin status rail, pinned + collapsible"`

---

## Phase 3: New container drawer and shared setups (`feat/ui-glance-3-new-container`)

### Task 6: Backend size presets and shared-setup listing

**Files:**
- Modify: `backend/app/services/settings_store.py` (new spec `CONTAINER_SIZE_PRESETS`, type `"json"`, group `"quota"`, default exactly as in the spec)
- Modify: `backend/app/routers/templates.py` (`GET /api/templates?shared=1` returns shared templates for any signed-in user; create, update and delete with `shared=True` are admin-only)
- Test: `backend/tests/test_size_presets.py`, `backend/tests/test_templates_shared.py`

**Interfaces:**
- Produces:
  - `GET /api/system/size-presets` → `[{id, label, cpus, memory_gb, gpu}]`, readable by any signed-in user.
  - Validation: 1 to 6 presets, `cpus` from 1 to 64, `memory_gb` from 1 to 512, unique `id`s.

- [ ] **Step 1:** Tests:
  - With no override, the default preset list equals the spec JSON.
  - A PUT with a duplicate `id` returns 422.
  - A non-admin POSTing a template with `shared=true` gets 403.
  - A non-admin can list shared templates.
- [ ] **Step 2:** Run `cd backend && .venv/bin/python -m pytest tests/test_size_presets.py tests/test_templates_shared.py -q`. Expected: FAIL.
- [ ] **Step 3:** Implement. Add a `"json"` type to `settings_store` with a validator hook.
- [ ] **Step 4:** Rerun. Expected: PASS. Then run the full backend gate.
- [ ] **Step 5:** `git commit -m "feat(backend): container size presets + shared setups for users"`

### Task 7: NewContainerDrawer (pick step, then launch step)

**Files:**
- Create: `frontend/src/components/launch/new-container-drawer.tsx`, `catalog-grid.tsx`, `setups-row.tsx`, `launch-step.tsx`
- Modify: `frontend/src/App.tsx` (the drawer replaces the Template gallery tab and `LaunchModal`)
- Delete: `frontend/src/components/templates/template-grid.tsx`, `registry-browser.tsx`, `launch-modal.tsx`. Keep `env-editor.tsx` and `builder/` for the Advanced section.
- Test: `frontend/src/components/launch/__tests__/new-container-drawer.test.tsx`

**Interfaces:**
- Consumes: `useRegistry` (LSIO list), `useTemplates({ shared: true })`, `GET /api/system/size-presets`, and the existing create-instance mutation.
- Produces: `NewContainerDrawer({ open, onClose })`.

- [ ] **Step 1:** Tests:
  - Opening the drawer focuses search.
  - Typing "fire" filters the catalog to Firefox, and hides "Your setups" while searching.
  - Clicking a catalog card shows the launch step with the title "Launch Firefox" and Standard preselected.
  - Clicking Launch calls create with `cpu_limit: "4"` and `memory_limit: "4g"`.
  - Esc closes the drawer.
  - The "Save as a setup" checkbox is absent for non-admins.
- [ ] **Step 2:** Run the tests. Expected: FAIL.
- [ ] **Step 3:** Implement to match the drawer in `c5-glance.html` (`.drawer`, `.cats`, `.catalog`, `.cfg`, `.presets`). Map presets to the instance fields `cpu_limit` (`String(cpus)`), `memory_limit` (`` `${memory_gb}g` ``) and `gpu_enabled`.
- [ ] **Step 4:** Run the tests and `npm run build`. Expected: PASS.
- [ ] **Step 5:** `git commit -m "feat(frontend): New container drawer, LSIO-first with shared setups"`

---

## Phase 4: Admin shell and settings (`feat/ui-glance-4-admin`)

### Task 8: Admin layout, side nav, find, unsaved-changes guard

**Files:**
- Modify: `frontend/src/components/settings/settings-layout.tsx`, `settings-nav.tsx`, `nav-config.tsx` (groups and labels exactly as in the spec)
- Create: `frontend/src/components/settings/unsaved-context.tsx`
- Test: `frontend/src/components/settings/__tests__/settings-nav.test.tsx` (extend the existing file)

**Interfaces:**
- Produces: `UnsavedProvider` and `useUnsaved(): { count: number; setCount(n): void; confirmLeave(): boolean }`. The nav calls `confirmLeave()` before switching section.

- [ ] **Step 1:** Tests:
  - Typing "rate" in "Find a setting" leaves only "Security and limits" visible.
  - The active item has `aria-current="page"` and class `gold-underline`.
  - With `count=3`, clicking another section opens the confirm dialog "Discard 3 unsaved changes?". Choosing Cancel keeps the current section.
- [ ] **Step 2:** Run the tests. Expected: FAIL.
- [ ] **Step 3:** Implement. The nav is sticky at `top: 82px`. The content `max-width` is 1640px. The status rail is passed `forceCollapsed` when the Admin tab is active.
- [ ] **Step 4:** Run the tests. Expected: PASS.
- [ ] **Step 5:** `git commit -m "feat(frontend): admin side nav with find + unsaved guard"`

### Task 9: Settings grid, rows and save pill

**Files:**
- Create: `frontend/src/components/settings/setting-field.tsx` (replaces `system/setting-row.tsx`), `save-pill.tsx`, `units.ts`
- Modify: `frontend/src/components/system/system-settings-panel.tsx` (render the backend groups as cards in a grid; keep its existing batch `updateMutation`)
- Test: `frontend/src/components/settings/__tests__/units.test.ts`, `setting-field.test.tsx`, `save-pill.test.tsx`

**Interfaces:**
- Produces:
  - `toDisplay(key, raw): { value: number; unit: string }` and `fromDisplay(key, value): number`. Seconds become min, hours or days using a per-key table in `units.ts`: `LOCKOUT_DURATION` → min, `BAN_DURATION` → hours, `REFRESH_TTL` → days, `ACCESS_TTL` → min. Rate strings `"5/60"` become `5 per min`.
  - `SavePill({ count, onSave, onDiscard, saving })`.

- [ ] **Step 1:** Tests:
  - `toDisplay("BAN_DURATION", 86400)` gives `{value: 24, unit: "hours"}`, and `fromDisplay` reverses it.
  - `toDisplay("RATE_LIMIT_AUTH", "5/60")` gives `{value: 5, unit: "per min"}`.
  - Editing a field adds `data-changed` and shows the ↺ button; clicking ↺ restores the value.
  - SavePill is hidden at count 0 and shows "1 unsaved change" (singular) at count 1.
  - The number inputs have class `no-spin`.
- [ ] **Step 2:** Run the tests. Expected: FAIL.
- [ ] **Step 3:** Implement the row grid `minmax(0,1fr) 138px 22px` and the card grid `repeat(auto-fill,minmax(360px,1fr))`, matching `shots/set-sec-1440.png`.
- [ ] **Step 4:** Run the tests and `npm run build`. Expected: PASS.
- [ ] **Step 5:** `git commit -m "feat(frontend): dense settings grid with units, reset, save pill"`

### Task 10: Users and groups table; Streaming page

**Files:**
- Modify: `frontend/src/components/system/users-panel.tsx` (dense table, inline role select, filter segments, hover actions), `groups-panel.tsx` (merged under the same nav item as a second table section)
- Modify: `frontend/src/components/system/workstations-panel.tsx` (rows: thumbnail, name + status/agent version, GPU and memory meters, Manage; "Enroll a workstation" as the `btn-gold` action in the SectionHead)
- Create: `frontend/src/components/system/streaming-page.tsx`. It merges `workstation-stream-settings.tsx` (per-workstation overrides become table rows), `turn-setup-guide.tsx` (becomes the Check setup dialog) and `turn-cost-card.tsx` (becomes the usage meter).
- Test: `frontend/src/components/system/__tests__/users-panel.test.tsx`, `streaming-page.test.tsx`

**Interfaces:**
- Consumes: the existing users API, `WEBRTC_*`, `TURN_*` and `CLOUDFLARE_*` settings, and the per-workstation `stream_settings`.
- Produces: `StreamingPage()`. An override cell renders "Default (X)" when the value is inherited; an overridden cell gets class `override`, styled gold.

- [ ] **Step 1:** Tests:
  - The Users "Locked 1" filter shows only locked rows, and Unlock calls the unlock API.
  - On Streaming, the GAME-01 codec cell shows `AV1` with class `override`, and the mini connection cell shows "Default (WebRTC)".
  - Changing the Codec segment marks the form dirty, so the save pill count is 1.
- [ ] **Step 2:** Run the tests. Expected: FAIL.
- [ ] **Step 3:** Implement to match `shots/set-str-1440.png`.
- [ ] **Step 4:** Run the tests and `npm run build`. Expected: PASS.
- [ ] **Step 5:** `git commit -m "feat(frontend): users table + unified Streaming page"`

---

## Phase 5: Metrics backend (`feat/ui-glance-5-metrics`)

### Task 11: Hourly rollups, stream sessions and stats endpoints

**Files:**
- Modify: `backend/app/models.py`. Add `MetricHour(ts_hour: datetime PK, cpu_avg, cpu_max, ram_avg, disk_pct, live_max: int)` and `StreamSession(id, user_id, target_kind: "workstation" | "instance", target_id, started_at, ended_at | None, transport, codec, relayed: bool, relay_reason: str | None)`.
- Modify: `backend/app/services/metrics_store.py`. Roll up every hour into `MetricHour` and keep 90 days. Extend `get_history` with `"7d"` and `"30d"` (read from `MetricHour`).
- Create: `backend/app/services/stream_sessions.py` with `open_session(...)`, `close_session(...)`, `streaming_hours(days, top=5)` and `sessions_per_day(days)`. It is hooked into the workstation connect and disconnect paths in `routers/workstations.py`/`agent.py` and the instance session monitor.
- Modify: `backend/app/services/turn_usage.py`. Add `daily_bytes(days=30)`, `monthly_bytes(months=6)` and `relay_reasons(month)`. The agent heartbeat already reports a relay delta; add a `relay_reason` value (`"strict_nat" | "firewall" | "mobile" | "unknown"`) taken from the selected ICE candidate pair type the agent sends.
- Create: `backend/app/routers/stats.py` (admin-only): `GET /api/admin/stats/overview?range=24h|7d|30d`, `GET /api/admin/stats/streaming?days=7&top=5`, `GET /api/admin/stats/relay?period=this|last|6m`.
- Tests: `backend/tests/test_metric_rollup.py`, `test_stream_sessions.py`, `test_stats_api.py`

**Interfaces:**
- Produces these JSON shapes, which the frontend relies on:
  - overview: `{tiles: {cpu: {now, series[24]}, ram: {...}, disk: {...}, live: {...}}, health_hours: ["ok" | "warn" | "fail"] x 24, load: {labels[], cpu[], ram[]}, sessions_per_day: [{date, count}] x 14}`
  - streaming: `{rows: [{workstation, sub, parts: {username: hours}}]}`. This is raw data; folding happens in the frontend.
  - relay: `{used_gb, free_gb, projected_gb, est_usd, budget_usd, relayed_pct, daily: [{date, gb}], monthly: [{month, gb}], by_user: [{name, gb}], by_workstation: [{name, gb}], reasons: [{reason, sessions}]}`

- [ ] **Step 1:** Tests:
  - Rolling up 120 samples of cpu 10 and 30 produces one `MetricHour` with `cpu_avg == 20` and `cpu_max == 30`.
  - Rows older than 90 days are deleted.
  - `streaming_hours(7)` sums the open session up to now.
  - A session that started before the window is clipped to the window.
  - `/stats/relay` returns 404 when `cf_turn_usage.configured()` is false.
  - A non-admin gets 403 on every stats endpoint.
- [ ] **Step 2:** Run `cd backend && .venv/bin/python -m pytest tests/test_metric_rollup.py tests/test_stream_sessions.py tests/test_stats_api.py -q`. Expected: FAIL.
- [ ] **Step 3:** Implement. Create tables with `SQLModel.metadata.create_all`, the existing pattern in `database.py`, and add an index on `StreamSession.started_at`.
- [ ] **Step 4:** Run the full backend gate. Expected: PASS.
- [ ] **Step 5:** `git commit -m "feat(backend): metric rollups, stream session log, admin stats API"`

---

## Phase 6: Overview and Relay cost pages (`feat/ui-glance-6-charts`)

### Task 12: Chart components, Overview and Relay cost

**Files:**
- Create: `frontend/src/components/charts/` with `line-chart.tsx`, `bar-chart.tsx`, `hbar-stack.tsx`, `sparkline.tsx`, `tooltip.tsx`, `axis.ts` (nice ticks), `fold-top.ts`. Replace `components/instances/sparkline.tsx` with an import of the new one.
- Modify: `frontend/src/components/system/metrics-overview.tsx` (tiles with sparklines, the three charts, lists)
- Create: `frontend/src/components/system/relay-cost-page.tsx`
- Modify: `frontend/src/components/settings/nav-config.tsx` (the "Relay cost" item has `visible: (cfg) => cfg.cfAnalytics`)
- Tests: `frontend/src/components/charts/__tests__/fold-top.test.ts`, `axis.test.ts`, `sparkline.test.tsx`, `line-chart.test.tsx`, `frontend/src/components/system/__tests__/relay-cost-page.test.tsx`

**Interfaces:**
- Consumes: the Task 11 endpoints.
- Produces:
  - `foldTop<T>(rows: T[], n: number, value: (r: T) => number): (T | { label: "Others"; sub: string; others: T[] })[]`
  - `foldSeries(rows: { parts: Record<string, number> }[], n): { series: { name: string; slot: "s1" | "s2" | "s3" | "s4" | "s5" | "s0" }[]; rows }`
  - `niceTicks(max: number, count = 4): number[]`

- [ ] **Step 1:** Tests:
  - `foldTop` with 12 rows and n=5 returns 6 rows, the last being `{label: "Others", sub: "7 more"}`.
  - `foldSeries` gives the top-5 users slots s1 to s5 in descending order of total and folds the rest into "Others" with slot s0. Its colour assignment is stable when the input order is shuffled.
  - `niceTicks(5)` returns `[0, 1, 2, 3, 4, 5]` or `[0, 2, 4, 6]`, never 1.3 or 3.8 (this fixes the mockup's axis bug).
  - `Sparkline` with `data=[]` renders "No data yet".
  - `LineChart` has a tooltip that names the series ("CPU 22%"), not "Value".
  - `RelayCostPage` shows 5 tiles and 5 charts, and its "Show as table" option reveals a `<table>`.
  - Nav: with `cfAnalytics=false` there is no "Relay cost" item.
- [ ] **Step 2:** Run the tests. Expected: FAIL.
- [ ] **Step 3:** Port from `docs/design/ui-rework-2026-11/charts.js`: 2px lines, 4px rounded bar ends, a 2px gap between stack segments, dashed recessive grid, legend present for 2 or more series, and the text in ink colour (never the series colour). Charts in a row share the row height (`.chart` is a flex column and `.plot` uses `flex: 1`). The tooltip is one portal element.
- [ ] **Step 4:** Run the tests and `npm run build`. Expected: PASS. Compare against `shots/viz-overview.png`, `viz-relay.png` and `spark.png`.
- [ ] **Step 5:** `git commit -m "feat(frontend): overview charts + sparklines, Relay cost page"`

---

## Phase 7: Login (`feat/ui-glance-7-login`)

### Task 13: Waves, dither sun, glyph beams, reveal and layout

**Files:**
- Create: `frontend/src/lib/effects/waves.ts`, `dither-sun.ts`, `glyph-beams.ts`
- Modify: `frontend/src/components/auth/LoginBrandPanel.tsx` (headline only; logo removed), `frontend/src/pages/LoginPage.tsx` (grid `minmax(0,1fr) minmax(400px, min(40vw,620px))`, logo at the top-left of the form panel, glass Sign in)
- Delete: `frontend/src/components/auth/RippleCanvas.tsx` (replaced by `waves.ts`)
- Modify: `frontend/package.json` (add `@fontsource/ibm-plex-mono`)
- Tests: `frontend/src/lib/effects/__tests__/dither-sun.test.ts`, `glyph-beams.test.ts`, `frontend/src/pages/__tests__/LoginPage.test.tsx` (extend the existing file)

**Interfaces:**
- Produces:
  - `createWaves(canvas, { lines: 28, top: 0.42 }): Effect`
  - `renderDitherSun(W, H, dpr, dark, horizonY): HTMLCanvasElement` (cached per size and theme)
  - `createGlyphBeams(canvas, { calmRects: () => DOMRect[] }): Effect`
  - `type Effect = { destroy(): void }`

- [ ] **Step 1:** Tests:
  - `renderDitherSun` on a 400×300 canvas with `horizonY=126` has zero opaque pixels below y=126 (uses jsdom with `canvas` mocked through `getImageData` stubs, or test the pure `ditherMask(W, H, …): Uint8Array` the function builds on).
  - `beamIntensity(x, y, t)` (pure, exported) is periodic, with period 230px along the 45° axis.
  - Glyph cells inside a calm rect get alpha 0.
  - LoginPage: there is no "Secure remote desktops" text, the logo sits inside the form panel, and the headline has class `reveal`.
- [ ] **Step 2:** Run the tests. Expected: FAIL.
- [ ] **Step 3:** Port from `login-waves.html` with the exact constants: dither cells 5px; dots of radius 1.1px; horizon gap 18px; fade 36px; beam period 230px, width 34px, speed 85px/s; the reveal keyframe `blur(16px)` to 0 over 2.2s with `cubic-bezier(.25,.6,.3,1)`. Light mode keeps the dark underline and the dark bronze edge.
- [ ] **Step 4:** Run the tests and `npm run build`. Expected: PASS. Compare against `shots/login-waves.png` and `login-waves-light.png`.
- [ ] **Step 5:** `git commit -m "feat(frontend): Glance login: gold waves, dither sun, glyph beams"`

---

## Done when

All 7 PRs are merged with green CI (both GitHub and GitLab pipelines), `docs/ADMIN.md` screenshots are refreshed, and the open-brain project context is updated with the new layout and endpoints.
