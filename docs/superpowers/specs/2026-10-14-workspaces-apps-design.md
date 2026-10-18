# Workspaces & Apps: split home, dock quick nav, open preference — design

Date: 2026-10-14 · Branch: `feat/workspaces-apps` (local, off `feat/service-favicons`) · Status: approved in chat

## 1. Intent

Two kinds of things live in Styx and the home page mixes them:

- **Workspaces** — things you stream: enrolled physical **workstations** and Selkies-template
  **instances** (containers).
- **Apps** — everything else: proxied web services (SP1/SP1.5).

Goals (user's words, condensed): separate the two cleanly; give the app shell's expanding tray (dock)
a quick switch between Workspaces and Apps; open things in a new tab by default, but ask once and save
the user's choice.

Success: a user can tell at a glance where desktops and apps live, hop from an app to another app or
to a workspace from the dock, and is asked about tabs exactly once per group.

Out of scope: a tray on workstation/instance stream pages (different origin, agent rollout — possible
follow-up); admin-level defaults for the open preference; renaming backend models or Settings sections.

## 2. Naming

User-facing names are **Workspaces** and **Apps**. Sub-headings inside Workspaces: **Workstations**
and **Instances**. Code identifiers may keep `service`/`instance`/`workstation`; only UI copy changes.
Settings → Services keeps its name (admin configuration of apps).

## 3. Home page

- A two-tab switch at the top of the home view: **Workspaces** | **Apps** (accessible tabs: `role=tablist`,
  arrow keys move between tabs, the selected tab has `aria-selected`).
- The last selected tab is remembered per browser (`localStorage` key `styx.home.tab`, wrapped in
  try/catch; default **Workspaces** when unset or unreadable).
- **Workspaces tab:** the current workspace layout without the services list — left list with
  sub-headings **Workstations** (existing `WorkstationList`) then **Instances** (existing `InstanceGrid`),
  detail pane on the right (unchanged behaviour, including narrow-screen overlay). The "+ New"
  (launch template) action stays here.
- **Apps tab:** a grid of app tiles (existing tile: favicon icon, name, health dot, "Needs setup" chip
  for admins) laid out roomier than today's list column. Admins get an **Add app** tile that opens
  Settings → Services (existing `onOpenSettings` path). Empty state: admins — "No apps yet. Add your
  first app." with the add action; members — "No apps shared with you yet."
- Both tabs always render, each with its own empty state (no hidden tabs), so the layout is stable.
- The existing home "tips" banner for admins (dismissible) moves to the Apps tab.

## 4. Dock (app shell only)

- The dock gains a segmented switch at its top: **Apps** | **Workspaces**. It opens on **Apps**.
  The switch is a tablist like the home tabs; focus handling from SP1.5 (focus first item on open,
  return focus to the edge tab on close, Escape closes) applies to the active list.
- **Apps list:** unchanged — clicking another app swaps the frame in place. The open preference is
  never consulted here (the dock exists for in-place switching).
- **Workspaces list:** workstations and instances the user can access, each with name, icon (workstation
  icon / template icon) and a status dot + text: workstation `online` / `offline` / `in use`; instance
  `running` / `stopped` / other states as reported. Clicking an available one opens it per the
  **Workspaces** open preference (§5). Unavailable ones (offline, stopped) are listed but disabled with
  their status; starting/waking happens from the home page only.
- Data: the shell fetches the same endpoints the home page uses for workstations and instances
  (no new backend list endpoint). Polling follows the existing dock tile refresh (30 s).
- **Home** link stays at the bottom of the dock.

## 5. Open preference

### Data
- `users` gains two nullable columns (additive migration in the existing column-migration list):
  `open_workspaces` and `open_apps`, each `NULL` (not chosen) | `'new_tab'` | `'same_tab'`.
- `GET /api/auth/me` returns both (`UserOut.open_workspaces`, `UserOut.open_apps`).
- `PUT /api/auth/me/preferences` — body `{ "open_workspaces"?: "new_tab"|"same_tab"|null,
  "open_apps"?: "new_tab"|"same_tab"|null }`; only provided keys change; signed-in user only; CSRF like
  other authenticated writes; 422 on any other value; returns `UserOut`. No admin override, no audit
  entry (personal UI preference).

### Prompt (preference for that group is `NULL`)
- Dialog title `Open <name>`; buttons **Open in new tab** (primary, focused by default — Enter picks it)
  and **Open here**; checkbox **Remember for all apps** / **Remember for all workspaces**, checked by
  default.
- Choosing opens the item; if Remember is checked, saves the group's preference (fire-and-forget PUT;
  on failure a toast "Couldn't save your choice" — the open still happens).
- Escape / close (✕) cancels: nothing opens, nothing is saved.
- Triggered from: home Apps tiles (Apps preference), home workstation **Connect** and instance **Open**
  actions (Workspaces preference), dock Workspaces list (Workspaces preference). Never from the dock
  Apps list.

### Opening
- **Apps, new tab:** `window.open(shellHref(tile), "_blank", "noopener")` during the click.
- **Apps, same tab:** current behaviour (navigate to `shellHref`).
- **Workspaces, new tab:** the stream URL comes from an async connect call, and browsers block
  `window.open` after an await. So the click synchronously opens a new tab on a same-origin
  **connecting page** (the existing "Connecting to …" wipe screen, served as a route, e.g.
  `/connecting?name=…`), keeps the returned window handle, then sets `handle.location` to the stream URL
  when connect resolves. On connect failure the tab shows the error message with a Close button; the
  takeover-confirm flow (workstation already in use) still runs in the original tab first, before any
  tab opens.
  - If `window.open` returns null (blocked), fall back to same-tab behaviour and toast
    "Your browser blocked the new tab, so Styx opened it here."
- **Workspaces, same tab:** current behaviour (in-place connecting wipe, then navigate).
- Modifier clicks (Ctrl/⌘/Shift/middle) on real links keep native browser behaviour and skip the prompt.

### Changing it later
- The user menu (avatar dropdown) gets an **Opening** group with two compact selectors:
  `Workspaces: New tab | This tab` and `Apps: New tab | This tab`. A `NULL` preference shows
  "Ask" as a third, selectable value (so a user can go back to being asked). Changes save immediately
  (same PUT) with an inline confirmation.

## 6. Error handling & edge cases
- Preference save fails → open proceeds, toast, preference stays unset (prompt again next time).
- `/me` not loaded yet → treat as unset only after it loads (no prompt flash; the click waits on the
  cached query, which is always loaded on the home page).
- Instance not running → its Open action already starts it; preference applies to the final open.
- A workspace removed or gone offline between list refresh and click → existing connect error path.

## 7. Testing
- **pytest:** preference columns migrate; `/me` exposes them; PUT accepts each value and null,
  ignores omitted keys, rejects others (422), requires auth + CSRF; another user's prefs untouched.
- **vitest:** home tabs (render, keyboard, persistence + unreadable storage fallback, empty states,
  admin Add app tile); dock switch (Apps default, Workspaces list states, disabled offline/stopped,
  Apps clicks never prompt); prompt (only when unset, Remember on/off, Escape cancels, save failure
  toast); workspace new-tab path opens synchronously and navigates the handle after connect, blocked
  popup fallback; user-menu Opening selectors incl. "Ask".
- **e2e:** first open of an app prompts → choose new tab + remember → second open doesn't prompt and
  opens a new page; dock lists workspaces and switches tabs; home tab persists across reload.

## 8. Files (expected)
- Backend: `models.py` (User columns), `database.py` (migration), `schemas.py` (`UserOut`, request
  model), `routers/auth.py` or a small `routers/me_prefs.py` (keep `auth.py` under 500 lines).
- Frontend: `components/instances/instance-workspace.tsx` (tabs), new `components/home/apps-grid.tsx`,
  `components/home/home-tabs.tsx`, `lib/open-pref.ts` (decide/open helpers), `components/open-prompt.tsx`,
  `shell/dock.tsx` (+ `shell/dock-workspaces.tsx`), user menu component, `api/client.ts`,
  connecting route/page reuse (`pages/ConnectingPage.tsx`).
