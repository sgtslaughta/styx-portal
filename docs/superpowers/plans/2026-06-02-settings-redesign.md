# Settings Area Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the stacked "System" tab with a polished **Settings** area — a left sidebar of categories (Account / Monitoring / Administration), each with tabbed sections, admin-gated, with tooltips/descriptions and subtle framer-motion.

**Architecture:** Pure frontend reorganization. A nav-config data module is the single source of truth for categories→sections (each section reuses an existing panel component unchanged). A `SettingsNav` sidebar + `SettingsLayout` shell render them, filter by role, animate transitions. No backend or API change.

**Tech Stack:** React 19, TypeScript, Tailwind v4, radix `Tooltip`/`Badge`, lucide icons, framer-motion (all existing deps).

**Verification:** presentational — each task verifies with `npx tsc --noEmit`; final task runs `npm run build` + manual checks. No unit tests.

---

## File Structure

**New:** `frontend/src/components/settings/nav-config.tsx`, `settings-nav.tsx`, `settings-layout.tsx`.
**Modified:** `frontend/src/App.tsx` (System block → `<SettingsLayout/>`, prune imports), `frontend/src/components/layout/tab-nav.tsx` (label "System"→"Settings").
**Deleted:** `frontend/src/components/system/metrics-dashboard.tsx` (its sub-tabs become sidebar sections; verify no other importer first).
**Reused unchanged:** `system/{metrics-overview,metrics-sessions,metrics-resources,metrics-logs,users-panel,oauth-providers-panel,image-manager,connected-accounts}.tsx`.

---

## Task 1: Nav config (single source of truth)

**Files:** Create `frontend/src/components/settings/nav-config.tsx`

- [ ] **Step 1: Create the config**

```tsx
import type { ComponentType } from "react";
import {
  Activity, Terminal, Cpu, ScrollText, Users, KeyRound, HardDrive,
  Link2, BarChart3, Shield, UserCircle,
} from "lucide-react";
import { MetricsOverview } from "@/components/system/metrics-overview";
import { MetricsSessions } from "@/components/system/metrics-sessions";
import { MetricsResources } from "@/components/system/metrics-resources";
import { MetricsLogs } from "@/components/system/metrics-logs";
import { UsersPanel } from "@/components/system/users-panel";
import { OAuthProvidersPanel } from "@/components/system/oauth-providers-panel";
import { ImageManager } from "@/components/system/image-manager";
import { ConnectedAccounts } from "@/components/system/connected-accounts";

export type SettingsSection = {
  id: string;
  label: string;
  icon: ComponentType<{ className?: string }>;
  description: string;
  tooltip: string;
  Component: ComponentType;
};

export type SettingsCategory = {
  id: string;
  label: string;
  icon: ComponentType<{ className?: string }>;
  adminOnly: boolean;
  sections: SettingsSection[];
};

export const CATEGORIES: SettingsCategory[] = [
  {
    id: "monitoring", label: "Monitoring", icon: BarChart3, adminOnly: true,
    sections: [
      { id: "overview", label: "Overview", icon: Activity,
        description: "Live system and instance health at a glance.",
        tooltip: "Aggregate CPU/RAM, instance counts, host info", Component: MetricsOverview },
      { id: "sessions", label: "Sessions", icon: Terminal,
        description: "Running instances and their lifecycle actions.",
        tooltip: "View and control active instances", Component: MetricsSessions },
      { id: "resources", label: "Resources", icon: Cpu,
        description: "Host resource usage over time.",
        tooltip: "CPU, memory, disk and GPU usage", Component: MetricsResources },
      { id: "logs", label: "Logs", icon: ScrollText,
        description: "Recent system and session events.",
        tooltip: "System event log", Component: MetricsLogs },
    ],
  },
  {
    id: "administration", label: "Administration", icon: Shield, adminOnly: true,
    sections: [
      { id: "users", label: "Users", icon: Users,
        description: "Manage user accounts, roles, and invitations.",
        tooltip: "Create or disable users; generate invites", Component: UsersPanel },
      { id: "sso", label: "SSO Providers", icon: KeyRound,
        description: "Configure OIDC / OAuth identity providers.",
        tooltip: "Add and manage single sign-on providers", Component: OAuthProvidersPanel },
      { id: "images", label: "Images", icon: HardDrive,
        description: "Pulled Docker images and cleanup.",
        tooltip: "List and remove cached images", Component: ImageManager },
    ],
  },
  {
    id: "account", label: "Account", icon: UserCircle, adminOnly: false,
    sections: [
      { id: "connected", label: "Connected accounts", icon: Link2,
        description: "Link external sign-in providers to your account.",
        tooltip: "Link or unlink Google, GitHub, and other providers", Component: ConnectedAccounts },
    ],
  },
];

export function visibleCategories(isAdmin: boolean): SettingsCategory[] {
  return CATEGORIES.filter((c) => isAdmin || !c.adminOnly);
}
```

- [ ] **Step 2: Type-check**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/settings/nav-config.tsx
git commit -m "feat(settings): nav config (categories/sections, role gating)"
```

---

## Task 2: Sidebar nav (motion + tooltips + admin badge)

**Files:** Create `frontend/src/components/settings/settings-nav.tsx`

- [ ] **Step 1: Create the component**

```tsx
import { useState } from "react";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { ChevronDown } from "lucide-react";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Tooltip, TooltipTrigger, TooltipContent } from "@/components/ui/tooltip";
import type { SettingsCategory } from "./nav-config";

type Props = {
  categories: SettingsCategory[];
  activeId: string;
  onSelect: (id: string) => void;
};

export function SettingsNav({ categories, activeId, onSelect }: Props) {
  const reduce = useReducedMotion();
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({});

  return (
    <nav className="w-56 shrink-0 space-y-4">
      {categories.map((cat) => {
        const CatIcon = cat.icon;
        const isCollapsed = collapsed[cat.id];
        return (
          <div key={cat.id}>
            <button
              onClick={() => setCollapsed((c) => ({ ...c, [cat.id]: !c[cat.id] }))}
              className="flex w-full items-center gap-2 px-2 py-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground"
            >
              <CatIcon className="h-4 w-4" />
              <span className="flex-1 text-left">{cat.label}</span>
              {cat.adminOnly && (
                <Badge variant="outline" className="px-1.5 py-0 text-[10px]">Admin</Badge>
              )}
              <ChevronDown className={cn("h-3.5 w-3.5 transition-transform", isCollapsed && "-rotate-90")} />
            </button>
            <AnimatePresence initial={false}>
              {!isCollapsed && (
                <motion.ul
                  initial={reduce ? false : { height: 0, opacity: 0 }}
                  animate={{ height: "auto", opacity: 1 }}
                  exit={reduce ? undefined : { height: 0, opacity: 0 }}
                  transition={{ duration: 0.18, ease: "easeOut" }}
                  className="mt-1 space-y-0.5 overflow-hidden"
                >
                  {cat.sections.map((s) => {
                    const Icon = s.icon;
                    const active = s.id === activeId;
                    return (
                      <li key={s.id}>
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <button
                              onClick={() => onSelect(s.id)}
                              className={cn(
                                "relative flex w-full items-center gap-2 rounded-md px-3 py-1.5 text-sm transition-colors",
                                active
                                  ? "text-foreground"
                                  : "text-muted-foreground hover:bg-muted/40 hover:text-foreground",
                              )}
                            >
                              {active && (
                                <motion.span
                                  layoutId="settings-active"
                                  className="absolute inset-0 rounded-md bg-secondary"
                                  transition={reduce ? { duration: 0 } : { type: "spring", stiffness: 500, damping: 40 }}
                                />
                              )}
                              <Icon className="relative z-10 h-4 w-4" />
                              <span className="relative z-10">{s.label}</span>
                            </button>
                          </TooltipTrigger>
                          <TooltipContent side="right">{s.tooltip}</TooltipContent>
                        </Tooltip>
                      </li>
                    );
                  })}
                </motion.ul>
              )}
            </AnimatePresence>
          </div>
        );
      })}
    </nav>
  );
}
```

- [ ] **Step 2: Type-check**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors. (If framer-motion's `motion`/`AnimatePresence`/`useReducedMotion` are not found, confirm the import is `from "framer-motion"` — it is a direct dependency.)

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/settings/settings-nav.tsx
git commit -m "feat(settings): sidebar nav with motion indicator, tooltips, admin badge"
```

---

## Task 3: Settings shell (role filter + default + animated content)

**Files:** Create `frontend/src/components/settings/settings-layout.tsx`

- [ ] **Step 1: Create the component**

```tsx
import { useMemo, useState } from "react";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { SettingsNav } from "./settings-nav";
import { visibleCategories, type SettingsSection } from "./nav-config";
import { useAuth } from "@/hooks/use-auth";

export function SettingsLayout() {
  const { user, loading } = useAuth();
  const reduce = useReducedMotion();
  const cats = useMemo(() => visibleCategories(user?.role === "admin"), [user?.role]);
  const sections = useMemo(() => cats.flatMap((c) => c.sections), [cats]);
  const [activeId, setActiveId] = useState<string | undefined>(undefined);

  // default = first section of first visible category; clamp to a visible section
  const active: SettingsSection | undefined =
    sections.find((s) => s.id === activeId) ?? sections[0];

  if (loading) {
    return <div className="mx-auto h-64 max-w-6xl animate-pulse rounded-lg bg-muted/30" />;
  }
  if (!active) return null;

  const Section = active.Component;
  return (
    <div className="mx-auto flex max-w-6xl gap-6">
      <SettingsNav categories={cats} activeId={active.id} onSelect={setActiveId} />
      <div className="min-w-0 flex-1">
        <div className="mb-4">
          <h2 className="text-lg font-semibold">{active.label}</h2>
          <p className="text-sm text-muted-foreground">{active.description}</p>
        </div>
        <AnimatePresence mode="wait">
          <motion.div
            key={active.id}
            initial={reduce ? false : { opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={reduce ? undefined : { opacity: 0, y: -8 }}
            transition={{ duration: 0.18, ease: "easeOut" }}
          >
            <Section />
          </motion.div>
        </AnimatePresence>
      </div>
    </div>
  );
}
```

Note: when a non-admin has an `activeId` pointing at a now-hidden admin section, `sections.find` misses and it falls back to `sections[0]` (their default) — correct clamp.

- [ ] **Step 2: Type-check**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/settings/settings-layout.tsx
git commit -m "feat(settings): settings shell (role filter, default, animated content)"
```

---

## Task 4: Wire into App + rename tab + remove old dashboard

**Files:** Modify `frontend/src/App.tsx`, `frontend/src/components/layout/tab-nav.tsx`; Delete `frontend/src/components/system/metrics-dashboard.tsx`

- [ ] **Step 1: Replace the System tab block in App.tsx**

In `frontend/src/App.tsx`, replace the System block (currently):
```tsx
        <div className={activeTab === "system" ? "" : "hidden"}>
          <div className="mx-auto max-w-5xl space-y-6">
            {user?.role === "admin" && <UsersPanel />}
            {user?.role === "admin" && <OAuthProvidersPanel />}
            {user && <ConnectedAccounts />}
            <MetricsDashboard />
          </div>
        </div>
```
with:
```tsx
        <div className={activeTab === "system" ? "" : "hidden"}>
          <SettingsLayout />
        </div>
```
(Keep the tab `id` `"system"` — only the label changes, in Task 4 Step 2.)

- [ ] **Step 2: Update App.tsx imports**

Remove these now-unused imports from `frontend/src/App.tsx`:
```tsx
import { MetricsDashboard } from "@/components/system/metrics-dashboard";
import { UsersPanel } from "@/components/system/users-panel";
import { OAuthProvidersPanel } from "@/components/system/oauth-providers-panel";
import { ConnectedAccounts } from "@/components/system/connected-accounts";
```
Add:
```tsx
import { SettingsLayout } from "@/components/settings/settings-layout";
```
`useAuth`/`user` is still used elsewhere (header/logout) — leave it. If `user` becomes unused after this change, ESLint/tsc will flag it; in that case keep `const { user } = useAuth();` only if still referenced, otherwise remove the destructure to satisfy `noUnusedLocals`. Check `tsc` output and adjust.

- [ ] **Step 3: Rename the tab label**

In `frontend/src/components/layout/tab-nav.tsx`, change the system tab entry label:
```tsx
  { id: "system", label: "Settings" },
```
(Leave `id: "system"` unchanged so `activeTab === "system"` keeps working.)

- [ ] **Step 4: Delete the old dashboard (after confirming no importers)**

Run: `cd frontend && grep -rn "metrics-dashboard" src/ || echo "no importers"`
Expected: only matches inside `metrics-dashboard.tsx` itself (or "no importers"). If any OTHER file imports it, stop and report.
Then delete: `rm frontend/src/components/system/metrics-dashboard.tsx`

- [ ] **Step 5: Type-check + build**

Run: `cd frontend && npx tsc --noEmit && npm run build`
Expected: succeeds.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/App.tsx frontend/src/components/layout/tab-nav.tsx frontend/src/components/system/metrics-dashboard.tsx
git commit -m "feat(settings): mount SettingsLayout, rename tab to Settings, retire metrics-dashboard"
```

---

## Task 5: Frontend-design polish + final verification

**Files:** May refine `settings-nav.tsx`, `settings-layout.tsx` (visual only)

- [ ] **Step 1: Invoke the frontend-design skill**

Use the `frontend-design` skill. Study the existing design system (`globals.css` tokens; existing panels' Card usage) and refine the new settings shell for production polish WITHOUT changing behavior, the nav-config data, role gating, or motion semantics:
- Sidebar: spacing/typography, a subtle right-edge divider between sidebar and content (e.g. `border-r border-border pr-6`), refined active-pill contrast, focus-visible rings on buttons.
- Content pane: header hierarchy, comfortable max width, consistent padding with other tabs.
- Confirm tooltips render on the right and are legible in light/dark.
- Keep motion subtle and `useReducedMotion`-guarded (do not remove the guards).

- [ ] **Step 2: Responsive guard**

Ensure the layout does not break on narrow widths: make the sidebar `hidden` below `md` and render a compact horizontal section selector (a simple scrollable row of the visible sections) above the content, OR allow the flex container to wrap. Minimal, non-blocking. Verify the page is usable at ~375px wide.

- [ ] **Step 3: Type-check + build**

Run: `cd frontend && npx tsc --noEmit && npm run build`
Expected: succeeds, no new warnings beyond the pre-existing chunk-size advisory.

- [ ] **Step 4: Manual verification (report)**
- As **admin**: Settings tab opens on **Monitoring → Overview**; all three categories visible; each section renders its correct existing panel; section tabs animate on switch; the active-item pill slides; tooltips show on hover; "Admin" badge on Monitoring + Administration; category collapse animates.
- As **non-admin**: only **Account → Connected accounts** visible; no Monitoring/Administration entries; default lands on Connected accounts.
- **Reduced motion** (OS setting on): transitions are instant, content still switches.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/settings/
git commit -m "style(settings): polish settings shell + responsive sidebar"
```

---

## Self-Review notes (addressed)
- **Spec coverage:** sidebar categories + section tabs (T1-3), Account/Monitoring/Admin IA + gating via nav-config + `visibleCategories` (T1,3), default landing Monitoring/Overview for admins / Account for non-admins (T3 `sections[0]`), in-place rename "System"→"Settings" keeping tab id (T4), tooltips + descriptions (T1 data, T2 tooltip, T3 description header), admin badge (T2), subtle framer-motion with `useReducedMotion` (T2 indicator+collapse, T3 content), retire metrics-dashboard sub-tabs (T4), responsive + polish (T5). All covered.
- **Reused components are zero-prop named exports** (`MetricsOverview`, `MetricsSessions`, `MetricsResources`, `MetricsLogs`, `UsersPanel`, `OAuthProvidersPanel`, `ImageManager`, `ConnectedAccounts`) — verified against current source.
- **Type consistency:** `SettingsSection.Component` (capitalized, rendered as `<Section/>`), `visibleCategories(isAdmin)`, `SettingsNav` props `{categories, activeId, onSelect}`, shared `layoutId="settings-active"` — consistent across tasks.
- **No backend/test changes:** presentational; backend authz already protects the reused admin panels (defense in depth).
