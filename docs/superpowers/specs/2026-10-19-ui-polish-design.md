# UI polish — design

Date: 2026-10-19. Branch: `feat/ui-polish` (off main f708b2e, v2.2.1).
Source: owner brainstorm + screenshot audit (209 shots, styx-e2e mocks).

## Goal

Make the whole app feel first-class. The home page wastes 60% of its width
(the detail pane only knows instances), navigation has two stacked tab rows,
and Settings/Services/dock carry visual noise and missing states.

## Decisions (owner)

- Home layout **A**: master–detail. One left list, one right detail pane that
  handles both workstations and instances.
- **One top nav**: Workspaces · Apps · Templates · Settings. The Workspaces |
  Apps sub-tabs and "My instances" go away.
- Left list: **one scroll area, sticky group headers**, collapsible groups,
  one search over both kinds.
- Workstation pane: **rich card, no image** now. Last-frame preview needs the
  agent's gateway page (agent rollout) → deferred to the agent batch.
- Scope: whole app. Ship as **P1** (home + nav) first, then **P2–P4** in a
  second PR on the same branch line.

## P1 — Home and navigation

### 1. Top nav (`components/layout/tab-nav.tsx`, `header.tsx`, `home/home-tabs.tsx`)
- Items: Workspaces, Apps, Templates (was "Template gallery"), Settings.
- Workspaces and Apps are routes/tab values of the top nav; `HomeTabs`
  removed. The remembered home tab (`styx.home.tab`) keeps working: landing on
  home opens the last of Workspaces/Apps.
- "Log out" link moves into the account menu (last item).
- Global status pills (running/paused/stopped/error) leave the header; the
  Instances group header shows the same counts.
- Mobile: nav stays one row, horizontally scrollable, 44 px targets.

### 2. Left list (`instances/instance-workspace.tsx`, new `workspace-list.tsx`)
- One scroll container. Two groups, each with a sticky header:
  `Workstations · N` (sort menu) and `Instances · N` (status counts, filter,
  Select, + Launch).
- Headers toggle collapse (state per browser, `localStorage`, try/catch).
- One search box at top filters both groups (name, hostname/image).
- Unified row: icon, name, one secondary line, status dot. Workstation line:
  `In use by <user>` | `Offline · 2 days` | `<os pretty_name> · seen 4s ago`.
  Instance line: `Running · up 6d 5h` | `Stopped` | `Error · <short reason>`.
- Row click selects (pane). Connect lives in the pane, plus a hover/focus
  quick-connect icon on the row for one-click use.
- Existing instance features keep working: multi-select + bulk actions,
  dense/card modes collapse to the unified row in this list.
- Empty group: one line + action (admin: "Add a workstation" → Settings ›
  Workstations; "Launch an instance" → Templates).

### 3. Detail pane (`instances/instance-detail-pane.tsx` + new `workstation-detail-pane.tsx`)
- Selection is `{kind: "workstation" | "instance", id}`.
- Workstation pane:
  - Hero: large workstation icon/avatar on a tinted panel, status dot + label.
  - Title row: name, status text, `Open in new tab`, primary action.
  - Facts grid: System (os pretty_name), GPU (gpu_info), Display
    (display_server), Agent (version; "update available" if agent_outdated).
  - Footer line: `seen <relative>`; `last_error` shown in a warning callout.
  - States: online+free → **Connect**; in use by other → **Join** (with the
    existing shared-control confirm) and admin-only **Take over**; in use by
    self → **Reconnect**; offline → disabled, hero greyscale, "offline since"
    + last_error hint.
- Instance pane: unchanged content, same header/hero framing so both kinds
  look alike.
- Nothing selected: show the most recently opened workspace (id+kind stored
  per browser when Connect/Open is used); if none or gone, a short guide card
  with the two empty-state actions.
- Narrow screens: existing overlay + Back button pattern, for both kinds.

### 4. Formatting (`lib/utils.ts`)
- `formatDuration` → `6d 5h`, `3h 12m`, `45m` (largest two units). Drop the
  `↑` glyph. Drop the monospace image column from rows.

## P2 — Settings

5. **Settings shell** (`settings/settings-nav.tsx`, `nav-config.tsx`,
   `settings-layout.tsx`): sentence-case group headings, no ADMIN badges (the
   whole admin area is admin-only already), inner "Settings" item renamed
   "General", content uses available width (max ~1100 px).
6. **Services list**: drop the inner "Proxied services" card and repeated
   title; actions in the page header. Status dot gets a tooltip + small legend
   (healthy / not checked / failing). Mode chips: one neutral chip style;
   amber only for risk (bypass, TLS off, Focus).
7. **Service form**: section headings Address · Access · Advanced with
   anchors; fix the field label clipping under the sticky drawer header
   (scroll-margin-top).
8. **Mount failed**: Retry button + one-line next step.

## P3 — Shell and dock

9. Dock: search field when >8 items (filters as you type, Enter opens first);
   status dot legend via tooltip.
10. Connecting page: review against the same rules (copy, spacing, cancel).

## P4 — Global

11. Empty states: icon + one line + primary action for no apps, no
    workstations, no instances, no services (one shared `EmptyState`).
12. Touch targets ≥ 44 px on coarse pointers for icon buttons; one icon set
    (lucide), consistent stroke/size.
13. Mobile forms: sticky Save/Cancel footer like the services drawer.

## Out of scope

Login page (audit: polished). Service form wizard. Workstation last-frame
preview (agent batch). New backend fields (uptime, session history).

## Testing

- Vitest per component: list grouping, sticky header collapse persistence,
  search across kinds, selection kinds, pane state per workstation status
  (Connect/Join/Take over/Reconnect/disabled), recent-workspace fallback,
  `formatDuration` cases, nav items + account-menu logout.
- `npm run build` (tsc -b) + lint gate.
- e2e: update `workspaces.spec.ts`/`shots-home.spec.ts` for the new nav and
  pane; re-shoot desktop/mobile light/dark and compare against this spec.
- Files stay < 500 lines (split `instance-grid.tsx` logic if it grows).
