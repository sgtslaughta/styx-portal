# Settings Area Redesign — Design

Date: 2026-06-02
Status: Approved

## Context

The "System" top tab stacks four panels vertically (`UsersPanel`, `OAuthProvidersPanel`,
`ConnectedAccounts`, `MetricsDashboard` — the last with its own internal sub-tab bar:
overview/sessions/resources/logs/images). It has grown into a catch-all with no
hierarchy, mixed admin/user content, and no descriptions. Notably the metrics endpoints
are already admin-gated in the backend, so a non-admin currently sees a broken metrics
view.

This redesign turns it into a polished **Settings** area: a left sidebar of high-level
categories, each holding tabbed sections, with informative tooltips/descriptions,
admin-gated sensitive sections, and subtle motion throughout. It reuses the existing
panel components unchanged — only the navigation/shell is new.

### Locked decisions (with user)
- **IA:** three sidebar categories — Account / Monitoring / Administration.
- **Default landing:** Monitoring → Overview (the metrics dashboard) for admins; for
  non-admins (Account only) it falls to the first visible section (Connected accounts).
- **Placement:** in-place — rename the "System" top tab to "Settings"; no router change.
- **Motion:** subtle framer-motion throughout (section transitions, active-item indicator,
  category expand/collapse), respecting `prefers-reduced-motion`.

## Layout

Two-pane shell inside the Settings tab: left sidebar (categories → section items) + right
content pane (active section's description header + component).

```
Settings tab
┌ SIDEBAR ─────────────┬ CONTENT PANE ──────────────────────┐
│ ▾ Monitoring   (adm) │  <Section title>                    │
│    • Overview  ●     │  <one-line description>             │
│    • Sessions        │  ───────────────────────────────    │
│    • Resources       │  <existing panel component>         │
│    • Logs            │                                     │
│ ▾ Administration(adm)│                                     │
│    • Users           │                                     │
│    • SSO Providers   │                                     │
│    • Images          │                                     │
│ ▾ Account            │                                     │
│    • Connected accts │                                     │
└──────────────────────┴─────────────────────────────────────┘
```

## Information architecture + gating

| Category | Gate | Sections | Reused component |
|----------|------|----------|------------------|
| **Monitoring** | admin | Overview · Sessions · Resources · Logs | `metrics-overview`, `metrics-sessions`, `metrics-resources`, `metrics-logs` |
| **Administration** | admin | Users · SSO Providers · Images | `users-panel`, `oauth-providers-panel`, `image-manager` |
| **Account** | all users | Connected accounts | `connected-accounts` |

- Gating lives in the **nav config**: each category has `adminOnly`. `settings-layout`
  filters categories by `useAuth().user.role`; a non-admin never sees Monitoring/
  Administration entries. The reused components remain protected by the existing backend
  authz (defense in depth).
- **Default section** = first section of the first visible category (admins →
  Monitoring/Overview; non-admins → Account/Connected accounts).
- `metrics-dashboard.tsx`'s internal sub-tab bar is **retired**; its sections become
  first-class Monitoring sidebar items, and "Images" moves to Administration. The
  `metrics-*` section components are reused unchanged. `metrics-dashboard.tsx` is removed
  from `App.tsx` (and deleted if nothing else imports it).

## Components (new — each small, one responsibility)

| File | Responsibility | Depends on |
|------|----------------|-----------|
| `src/components/settings/nav-config.tsx` | single source of truth: `CATEGORIES` array of `{ id, label, icon, adminOnly, sections: [{ id, label, icon, description, tooltip, render }] }` where `render` returns the section's component | the reused panels, lucide icons |
| `src/components/settings/settings-nav.tsx` | sidebar: renders visible category groups → section items; active highlight (motion `layoutId` indicator); per-item tooltip; "Admin" badge on gated categories; expand/collapse | nav-config, useAuth, ui/tooltip, framer-motion |
| `src/components/settings/settings-layout.tsx` | the shell: computes visible categories from role, owns `activeSection` state, computes the default, renders sidebar + animated content pane (description header + section component) | settings-nav, nav-config, useAuth, framer-motion |

`App.tsx` change: the Settings tab content becomes `<SettingsLayout />` (replacing the four
stacked panels + MetricsDashboard); the top-tab label "System" → "Settings" in
`tab-nav.tsx` (keep the tab `id` as `"system"` to avoid churn, or rename to `"settings"` —
implementer's choice as long as App + TabNav agree).

## Data model
None. Pure frontend reorganization; no API or backend change. All section components keep
their current data fetching (React Query) untouched.

## Motion (framer-motion, subtle)
- **Section transition:** on `activeSection` change, cross-fade + small slide
  (`AnimatePresence` with `motion.div`, `initial={{opacity:0, y:8}}` → `animate={{opacity:1,
  y:0}}` → `exit={{opacity:0, y:-8}}`, ~150–200ms, ease-out). Key by section id.
- **Active sidebar indicator:** a `motion.div` with shared `layoutId="settings-active"`
  slides the highlight pill between items.
- **Category expand/collapse:** animate height/opacity of the section list
  (`AnimatePresence` + `motion.ul`).
- **Hover affordance:** subtle `whileHover` on sidebar items (e.g. background fade; avoid
  large scale).
- **Reduced motion:** gate non-essential animation behind `useReducedMotion()` — fall back
  to instant show/hide; never block content on animation.

## Tooltips + descriptions
- Each **section** carries a one-line `description` rendered as a muted subheader at the
  top of the content pane (e.g. Users → "Manage user accounts, roles, and invitations";
  SSO Providers → "Configure OIDC/OAuth identity providers"; Connected accounts → "Link
  external sign-in providers to your account").
- Each **sidebar item** has a short `tooltip` shown via the existing radix `Tooltip`
  (TooltipProvider already wraps the app) on hover/focus of an info affordance or the label.
- Admin-only categories show a small "Admin" `Badge`.

## Behavior / edge cases
- While `useAuth().loading`: render a lightweight skeleton (sidebar placeholder), no flph.
- Non-admin: sidebar shows only Account; no empty Monitoring/Administration headers; default
  section is Connected accounts.
- Role changes / re-login: layout recomputes visible categories and clamps `activeSection`
  to a visible one (if the current active section becomes hidden, reset to default).
- Responsive: below ~`md`, sidebar collapses to a horizontal scroll row or a `Select` at the
  top of the pane (graceful; not blocking).
- Keyboard: sidebar items are buttons (focusable, Enter/Space activate); tab order
  sidebar → content.

## Testing
This is presentational; verification is type-check + build + manual.
- `npx tsc --noEmit` clean; `npm run build` succeeds.
- Manual: as admin — Settings opens on Monitoring/Overview; all three categories + all
  sections render the correct existing panel; tooltips/descriptions show; active indicator
  animates; section transitions animate. As a non-admin — only Account/Connected accounts
  visible; no admin sections reachable; backend still rejects any direct admin API call.
- Reduced-motion: with OS reduce-motion on, transitions are instant.

## Critical files to reuse
- `frontend/src/components/system/{users-panel,oauth-providers-panel,connected-accounts,image-manager,metrics-overview,metrics-sessions,metrics-resources,metrics-logs}.tsx` — rendered as sections.
- `frontend/src/components/ui/{tooltip,badge,card,button}.tsx` — primitives.
- `frontend/src/hooks/use-auth.ts` — role for gating + default.
- `frontend/src/App.tsx` (System-tab block) + `frontend/src/components/layout/tab-nav.tsx` — wiring + label.
- `frontend/src/styles/globals.css` — semantic tokens to match.
- framer-motion (existing dependency) — motion primitives + `useReducedMotion`.
