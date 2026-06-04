# Styx Portal Dashboard Theming Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the branded "immersive depth" Styx Portal aesthetic from the login pages into the whole dashboard via a token-first design-system change.

**Architecture:** Add brand/depth tokens + four reusable utility classes to `globals.css` (defined for both light and dark), then have dashboard components adopt those classes. The look is defined once; components only swap container classNames. No layout changes, no new animation, no backend changes. Rides on the existing root `ThemeProvider` so everything flips light/dark live.

**Tech Stack:** React 19, Tailwind v4 (`@import "tailwindcss"`, `@theme inline`, semantic tokens that flip on `.dark`), Vite.

**No test harness:** The frontend has no test runner. Verification each task = `npx tsc --noEmit` (no new errors) + `npm run build` (succeeds) + manual visual check in light AND dark. All commands run from `frontend/`.

**Reference:** spec at `docs/superpowers/specs/2026-06-04-styx-portal-dashboard-theming-design.md`.

---

## Phase 1 — Foundation

### Task 1: Add brand/depth tokens + utility classes to globals.css

**Files:**
- Modify: `frontend/src/styles/globals.css` (append after the existing `.styx-brand` block at end of file)

- [ ] **Step 1: Append tokens + utilities**

Add to the END of `frontend/src/styles/globals.css`:

```css
/* ── Styx Portal dashboard theming (immersive depth) ───────────────── */
:root {
  --surface-gradient: radial-gradient(120% 140% at 10% 0%, #eef3fb 0%, #e7ecf4 60%);
  --card-gradient: linear-gradient(160deg, #ffffff, #eef3fb);
  --card-border-color: #d4def0;
  --card-glow: 0 1px 2px rgba(40, 90, 200, 0.06), 0 8px 20px -14px rgba(40, 90, 200, 0.35);
  --brand-accent: #2f6fe0;
  --motif-color: rgba(40, 90, 200, 0.05);
  --header-gradient: linear-gradient(90deg, #e9eff8, #eef3fb);
}
.dark {
  --surface-gradient: radial-gradient(120% 140% at 10% 0%, #0c1322 0%, #0a0e17 60%);
  --card-gradient: linear-gradient(160deg, #121d30, #0d1420);
  --card-border-color: #213050;
  --card-glow: 0 1px 0 rgba(90, 150, 255, 0.08) inset, 0 6px 18px -10px rgba(40, 90, 200, 0.5);
  --brand-accent: #5b9bff;
  --motif-color: rgba(70, 140, 255, 0.06);
  --header-gradient: radial-gradient(120% 180% at 10% 50%, #0c1830 0%, #0a0f1a 60%);
}

.styx-app-bg { background: var(--surface-gradient); }

.styx-card {
  background: var(--card-gradient);
  border: 1px solid var(--card-border-color);
  box-shadow: var(--card-glow);
}

.styx-header {
  position: relative;
  overflow: hidden;
  background: var(--header-gradient);
}

/* Static river current — no animation (header motif). */
.styx-motif::before {
  content: "";
  position: absolute;
  inset: 0;
  pointer-events: none;
  background: repeating-linear-gradient(115deg, transparent 0 16px, var(--motif-color) 16px 17px);
  -webkit-mask: radial-gradient(120% 200% at 0% 50%, #000 30%, transparent 75%);
          mask: radial-gradient(120% 200% at 0% 50%, #000 30%, transparent 75%);
}
.styx-header > * { position: relative; z-index: 1; }
```

- [ ] **Step 2: Verify build + types**

Run: `cd frontend && npx tsc --noEmit && npm run build`
Expected: no type errors, build succeeds.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/styles/globals.css
git commit -m "feat(theme): add Styx Portal depth tokens + utility classes"
```

### Task 2: Apply page background in App shell

**Files:**
- Modify: `frontend/src/App.tsx:65`

- [ ] **Step 1: Add `.styx-app-bg` to the shell wrapper**

In `frontend/src/App.tsx`, the outer shell div is currently:

```tsx
    <div className="flex min-h-screen flex-col bg-background">
```

Change to:

```tsx
    <div className="flex min-h-screen flex-col bg-background styx-app-bg">
```

(Keep `bg-background` as a fallback under the gradient.)

- [ ] **Step 2: Verify**

Run: `cd frontend && npm run build`
Expected: succeeds.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/App.tsx
git commit -m "feat(theme): branded page background"
```

---

## Phase 2 — App chrome

### Task 3: Brand the header

**Files:**
- Modify: `frontend/src/components/layout/header.tsx` (the `<header>` JSX around line 56-72; imports line 1)

- [ ] **Step 1: Swap the icon import to Waves**

In `frontend/src/components/layout/header.tsx` line 1, the import is:

```tsx
import { Monitor, Moon, Sun } from "lucide-react";
```

Change to (add `Waves`; `Monitor` is still used by the theme toggle's "system" icon, keep it):

```tsx
import { Monitor, Moon, Sun, Waves } from "lucide-react";
```

- [ ] **Step 2: Restyle the header band + brand**

Replace the opening `<header>` and brand line. Current:

```tsx
    <header className="flex items-center gap-3 border-b border-border px-6 py-2.5">
      <Monitor className="h-5 w-5 text-primary" />
      <span className="text-base font-bold">Styx Portal</span>
```

Change to:

```tsx
    <header className="styx-header styx-motif flex items-center gap-3 border-b border-border px-6 py-2.5">
      <Waves className="h-5 w-5" style={{ color: "var(--brand-accent)" }} />
      <span className="text-base font-extrabold tracking-wider">STYX PORTAL</span>
```

- [ ] **Step 3: Verify**

Run: `cd frontend && npx tsc --noEmit && npm run build`
Expected: no new type errors, build succeeds.

- [ ] **Step 4: Manual check**

Run dev server (`cd frontend && npm run dev`); confirm header shows the Waves glyph in brand-blue, "STYX PORTAL" wordmark, a subtle static diagonal motif, and readable text in BOTH light and dark (toggle via the theme button).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/layout/header.tsx
git commit -m "feat(theme): branded header with river motif"
```

### Task 4: Restyle status chips (CountChip) in header

**Files:**
- Modify: `frontend/src/components/layout/header.tsx` (the `CountChip` component — locate it by name in the file)

- [ ] **Step 1: Read the file and locate `CountChip`**

Read `frontend/src/components/layout/header.tsx` fully and find the `CountChip` function. It renders a small count + label + colored dot.

- [ ] **Step 2: Give chips the pill treatment**

Update `CountChip`'s returned wrapper so it is a rounded pill consistent with the spec mockup: a `rounded-full` container with `border border-border bg-card/60 px-2 py-0.5 text-xs`, the existing colored dot (keep its `dotClass`), and the count+label. Preserve the component's existing props (`count`, `label`, `dotClass`) and the dot element exactly. Only the wrapper classes change — do NOT change which counts are shown or the props interface.

Example wrapper shape (adapt to the existing inner markup):

```tsx
    <span className="flex items-center gap-1.5 rounded-full border border-border bg-card/60 px-2 py-0.5 text-xs text-muted-foreground">
      <span className={cn("h-1.5 w-1.5 rounded-full", dotClass)} />
      <span className="tabular-nums text-foreground">{count}</span>
      {label}
    </span>
```

(If `cn` is not already imported in this file, add `import { cn } from "@/lib/utils";`.)

- [ ] **Step 3: Verify**

Run: `cd frontend && npx tsc --noEmit && npm run build`
Expected: no new type errors, build succeeds.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/layout/header.tsx
git commit -m "feat(theme): pill status chips in header"
```

### Task 5: Restyle the tab nav

**Files:**
- Modify: `frontend/src/components/layout/tab-nav.tsx:14-33`

- [ ] **Step 1: Replace the active/inactive tab styling**

Current button className block in `frontend/src/components/layout/tab-nav.tsx`:

```tsx
          className={cn(
            "px-4 py-2 text-sm font-medium transition-colors",
            "hover:text-foreground",
            activeTab === tab.id
              ? "border-b-2 border-primary text-foreground"
              : "text-muted-foreground"
          )}
```

Change to the pill style from mockup B:

```tsx
          className={cn(
            "my-1.5 rounded-lg px-4 py-1.5 text-sm font-medium transition-colors",
            "hover:text-foreground",
            activeTab === tab.id
              ? "bg-card text-foreground shadow-[inset_0_0_0_1px_var(--card-border-color)]"
              : "text-muted-foreground"
          )}
```

Also change the container to drop the bottom border (pills don't need it). Current:

```tsx
    <div className="flex gap-1 border-b border-border px-6">
```

Change to:

```tsx
    <div className="flex gap-1 border-b border-border px-6 styx-header">
```

(Keeps the divider line but adds the subtle branded band behind the tabs.)

- [ ] **Step 2: Verify + manual check**

Run: `cd frontend && npx tsc --noEmit && npm run build`
Expected: no new type errors, build succeeds. Then dev-server check: active tab is a tinted pill with inset ring, inactive tabs muted, both themes readable.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/layout/tab-nav.tsx
git commit -m "feat(theme): branded tab nav pills"
```

---

## Phase 3 — Instance surfaces

**Shared adoption pattern for Phase 3 & 4:** for each card/panel container that currently uses `bg-card` (often with `border border-border` and a `rounded-*`), replace `bg-card` and any sibling `border border-border` with the single class `styx-card`. Keep the `rounded-*`, padding, hover, layout, and all logic unchanged. `styx-card` provides background + border + glow. Where a hover border color is set (e.g. `hover:border-primary/50`), keep it — it layers on top.

### Task 6: Instance card + small card

**Files:**
- Modify: `frontend/src/components/instances/instance-card.tsx:39`
- Modify: `frontend/src/components/instances/instance-card-sm.tsx`

- [ ] **Step 1: instance-card.tsx — adopt styx-card**

Current container className (line ~39):

```tsx
      className="group cursor-pointer overflow-hidden rounded-xl border border-border bg-card transition-colors hover:border-primary/50"
```

Change to:

```tsx
      className="styx-card group cursor-pointer overflow-hidden rounded-xl transition-colors hover:border-primary/50"
```

- [ ] **Step 2: instance-card-sm.tsx — adopt styx-card**

Read `frontend/src/components/instances/instance-card-sm.tsx`. Find its outer card container using `bg-card` / `border border-border`. Apply the shared adoption pattern: replace `bg-card` + `border border-border` with `styx-card`, keep everything else.

- [ ] **Step 3: Verify**

Run: `cd frontend && npx tsc --noEmit && npm run build`
Expected: no new type errors, build succeeds.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/instances/instance-card.tsx frontend/src/components/instances/instance-card-sm.tsx
git commit -m "feat(theme): styx-card on instance cards"
```

### Task 7: Instance row, thumbnail, detail pane, grid

**Files:**
- Modify: `frontend/src/components/instances/instance-row.tsx`
- Modify: `frontend/src/components/instances/instance-thumbnail.tsx`
- Modify: `frontend/src/components/instances/instance-detail-pane.tsx`
- Modify: `frontend/src/components/instances/instance-grid.tsx`

- [ ] **Step 1: Apply the shared adoption pattern to each**

For each of the four files: read it, find any card/panel/row container using `bg-card` (with `border border-border`), and replace with `styx-card` per the shared pattern. If a file has NO `bg-card` container (e.g. `instance-grid.tsx` may be only a layout grid), leave it unchanged and note that in your report. Do not alter layout, data, or logic.

- [ ] **Step 2: Verify**

Run: `cd frontend && npx tsc --noEmit && npm run build`
Expected: no new type errors, build succeeds.

- [ ] **Step 3: Manual check**

Dev server: instance grid + detail pane render with gradient/glow cards in both themes; text readable; no broken layout.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/instances/instance-row.tsx frontend/src/components/instances/instance-thumbnail.tsx frontend/src/components/instances/instance-detail-pane.tsx frontend/src/components/instances/instance-grid.tsx
git commit -m "feat(theme): styx-card on instance row/thumbnail/detail/grid"
```

---

## Phase 4 — Templates + System

### Task 8: Template gallery + registry

**Files:**
- Modify: `frontend/src/components/templates/template-grid.tsx`
- Modify: `frontend/src/components/templates/registry-browser.tsx`
- Modify: `frontend/src/components/templates/registry-info.tsx`

- [ ] **Step 1: Apply the shared adoption pattern**

For each file: read it, find template/registry card containers using `bg-card` (+ `border border-border`), replace with `styx-card`. Keep badges, layout, logic. If a file has no such container, leave unchanged and note it.

- [ ] **Step 2: Verify**

Run: `cd frontend && npx tsc --noEmit && npm run build`
Expected: no new type errors, build succeeds.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/templates/template-grid.tsx frontend/src/components/templates/registry-browser.tsx frontend/src/components/templates/registry-info.tsx
git commit -m "feat(theme): styx-card on template + registry cards"
```

### Task 9: Stat tiles

**Files:**
- Modify: `frontend/src/components/common/stat-tile.tsx:16`

- [ ] **Step 1: Adopt styx-card in StatTile**

Current container (line 16):

```tsx
    <div className={cn("rounded-lg border border-border bg-card p-3", className)}>
```

Change to:

```tsx
    <div className={cn("styx-card rounded-lg p-3", className)}>
```

(Leave the `Gauge` component below unchanged.)

- [ ] **Step 2: Verify + commit**

Run: `cd frontend && npx tsc --noEmit && npm run build` → succeeds.

```bash
git add frontend/src/components/common/stat-tile.tsx
git commit -m "feat(theme): styx-card on stat tiles"
```

### Task 10: System panels + settings layout

**Files:**
- Modify: `frontend/src/components/settings/settings-layout.tsx`
- Modify: `frontend/src/components/system/metrics-overview.tsx`
- Modify: `frontend/src/components/system/metrics-resources.tsx`
- Modify: `frontend/src/components/system/metrics-sessions.tsx`
- Modify: `frontend/src/components/system/metrics-logs.tsx`
- Modify: `frontend/src/components/system/image-manager.tsx`
- Modify: `frontend/src/components/system/users-panel.tsx`
- Modify: `frontend/src/components/system/oauth-providers-panel.tsx`
- Modify: `frontend/src/components/system/connected-accounts.tsx`

- [ ] **Step 1: Apply the shared adoption pattern across system panels**

For each file: read it, find panel/card containers using `bg-card` (+ `border border-border`) and replace with `styx-card`. Many of these have multiple such containers — convert each. Keep tables, charts, forms, layout, and logic untouched. Files with no `bg-card` container: leave unchanged and note in report.

- [ ] **Step 2: Verify**

Run: `cd frontend && npx tsc --noEmit && npm run build`
Expected: no new type errors, build succeeds.

- [ ] **Step 3: Manual check**

Dev server → Settings tab: every sub-panel (overview/resources/sessions/logs/images/users/oauth/connected) renders with branded cards, readable in both themes, no layout breakage.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/settings/settings-layout.tsx frontend/src/components/system/
git commit -m "feat(theme): styx-card across system + settings panels"
```

---

## Final verification

- [ ] **Build + types:** `cd frontend && npx tsc --noEmit && npm run build` → clean.
- [ ] **Coverage sweep:** `grep -rn "bg-card" frontend/src/components/instances frontend/src/components/templates frontend/src/components/system frontend/src/components/common/stat-tile.tsx` — review remaining `bg-card` uses; each should be intentional (e.g. a sub-element, not a top-level card) and noted, not an accidental miss.
- [ ] **Manual full pass:** instances, templates, settings — light AND dark. Confirm: consistent gradient/glow cards, brand-blue accents, static header motif, readable contrast, no layout regressions.
- [ ] **Reduced-motion:** confirm nothing animates (static motif only).
