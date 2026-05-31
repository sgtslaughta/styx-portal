# Frontend Rework — Plan 1: Foundation & Primitives

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the shared design layer (status/chart/motion tokens) and reusable UI primitives (ConfirmDialog, Tooltip, Popover, Drawer, ActionBar, StatTile, Gauge, DataTable, SearchSortBar) that every later per-area refactor consumes.

**Architecture:** New files only, plus two small refactors (sparkline, status-badge) and one App.tsx wrapper add. Nothing in this plan changes data flow or existing component behavior beyond status-badge styling. Later plans (Instances, Templates, System, Shell) import these primitives.

**Tech Stack:** React 19, Tailwind 4 (semantic oklch tokens), `radix-ui` umbrella 1.4.3, framer-motion 12, lucide-react, class-variance-authority, sonner.

**Verification model:** The frontend has **no test runner** — `package.json` exposes only `lint` (`tsc --noEmit`) and `build` (`tsc -b && vite build`). Per-task verification = typecheck passes. Phase-end = full build passes + manual smoke. Do not add a test framework.

**Working directory for all commands:** `/home/user/code/remote-access/frontend`

---

## Task 1: Design tokens in globals.css

**Files:**
- Modify: `frontend/src/styles/globals.css`

- [ ] **Step 1: Add chart vars to `:root`**

In `:root` (after the `--idle:` line, before the closing `}`), add:

```css
  --chart-1: oklch(0.55 0.17 255);
  --chart-2: oklch(0.55 0.2 300);
  --chart-3: oklch(0.6 0.13 180);
  --chart-4: oklch(0.65 0.18 50);
```

- [ ] **Step 2: Add chart vars to `.dark`**

In `.dark` (after the `--idle:` line), add:

```css
  --chart-1: oklch(0.65 0.17 255);
  --chart-2: oklch(0.66 0.2 300);
  --chart-3: oklch(0.72 0.13 180);
  --chart-4: oklch(0.75 0.18 50);
```

- [ ] **Step 3: Map chart vars in `@theme inline` and tighten radius**

In the `@theme inline` block, add the chart color mappings (after `--color-idle:`), and change `--radius`:

```css
  --color-chart-1: var(--chart-1);
  --color-chart-2: var(--chart-2);
  --color-chart-3: var(--chart-3);
  --color-chart-4: var(--chart-4);
  --radius: 0.5rem;
```

(Replace the existing `--radius: 0.625rem;` line with `--radius: 0.5rem;`.)

- [ ] **Step 4: Typecheck**

Run: `npm run lint`
Expected: PASS (CSS isn't typechecked; this confirms nothing else broke).

- [ ] **Step 5: Commit**

```bash
git add src/styles/globals.css
git commit -m "feat(ui): add chart color tokens, tighten radius"
```

---

## Task 2: Status single-source-of-truth (`lib/status.ts`)

**Files:**
- Create: `frontend/src/lib/status.ts`

- [ ] **Step 1: Create the file**

```ts
import {
  Activity, AlertTriangle, Clock, Download, Loader2, Pause, Power, Square,
  type LucideIcon,
} from "lucide-react";

export type InstanceStatusValue =
  | "created" | "creating" | "pulling" | "starting" | "running"
  | "idle" | "paused" | "stopping" | "stopped" | "error";

export type StatusGroup =
  | "running" | "paused" | "transition" | "stopped" | "error";

export interface StatusMeta {
  label: string;
  /** Tailwind text color class, e.g. "text-success". */
  textClass: string;
  /** Tailwind background class for the status dot, e.g. "bg-success". */
  dotClass: string;
  icon: LucideIcon;
  /** Whether the dot/icon should pulse. */
  pulse: boolean;
  group: StatusGroup;
}

export const STATUS_META: Record<InstanceStatusValue, StatusMeta> = {
  created:  { label: "Created",  textClass: "text-muted-foreground", dotClass: "bg-muted-foreground", icon: Power,         pulse: false, group: "stopped" },
  creating: { label: "Creating", textClass: "text-primary",          dotClass: "bg-primary",          icon: Loader2,       pulse: true,  group: "transition" },
  pulling:  { label: "Pulling",  textClass: "text-primary",          dotClass: "bg-primary",          icon: Download,      pulse: true,  group: "transition" },
  starting: { label: "Starting", textClass: "text-primary",          dotClass: "bg-primary",          icon: Loader2,       pulse: true,  group: "transition" },
  running:  { label: "Running",  textClass: "text-success",          dotClass: "bg-success",          icon: Activity,      pulse: true,  group: "running" },
  idle:     { label: "Idle",     textClass: "text-warning",          dotClass: "bg-warning",          icon: Clock,         pulse: false, group: "running" },
  paused:   { label: "Paused",   textClass: "text-warning",          dotClass: "bg-warning",          icon: Pause,         pulse: false, group: "paused" },
  stopping: { label: "Stopping", textClass: "text-warning",          dotClass: "bg-warning",          icon: Loader2,       pulse: true,  group: "transition" },
  stopped:  { label: "Stopped",  textClass: "text-muted-foreground", dotClass: "bg-muted-foreground", icon: Square,        pulse: false, group: "stopped" },
  error:    { label: "Error",    textClass: "text-destructive",      dotClass: "bg-destructive",      icon: AlertTriangle, pulse: false, group: "error" },
};

export function statusMeta(status: string): StatusMeta {
  return STATUS_META[status as InstanceStatusValue] ?? STATUS_META.stopped;
}

export const RUNNING_STATUSES = new Set<string>(["running", "idle"]);
export const TRANSITION_STATUSES = new Set<string>(["creating", "pulling", "starting", "stopping"]);

export function isRunning(status: string): boolean { return RUNNING_STATUSES.has(status); }
export function isTransitioning(status: string): boolean { return TRANSITION_STATUSES.has(status); }
```

- [ ] **Step 2: Typecheck**

Run: `npm run lint`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add src/lib/status.ts
git commit -m "feat(ui): status metadata single source of truth"
```

---

## Task 3: Chart palette (`lib/chart.ts`)

**Files:**
- Create: `frontend/src/lib/chart.ts`

- [ ] **Step 1: Create the file**

```ts
/** Chart/sparkline series colors. Reference CSS vars from globals.css so they follow the theme. */
export const CHART_PALETTE = [
  "var(--chart-1)",
  "var(--chart-2)",
  "var(--chart-3)",
  "var(--chart-4)",
] as const;

export const CHART_COLORS = {
  cpu: "var(--chart-1)",
  memory: "var(--chart-2)",
  network: "var(--chart-3)",
  storage: "var(--chart-4)",
} as const;
```

- [ ] **Step 2: Typecheck**

Run: `npm run lint`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add src/lib/chart.ts
git commit -m "feat(ui): themable chart palette tokens"
```

---

## Task 4: Motion presets (`lib/motion.ts`)

**Files:**
- Create: `frontend/src/lib/motion.ts`

- [ ] **Step 1: Create the file**

```ts
import type { Transition, Variants } from "framer-motion";

/** Calm default spring for layout/position changes. */
export const spring: Transition = { type: "spring", stiffness: 400, damping: 32 };

/** Mount/unmount fade + small slide. Restrained — no scale pop. */
export const fadeSlideIn: Variants = {
  initial: { opacity: 0, y: 8 },
  animate: { opacity: 1, y: 0 },
  exit: { opacity: 0, y: -6 },
};

/** Hover lift for cards. */
export const hoverLift = { y: -2 } as const;

/** Stagger children in a list/grid. */
export const listStagger: Variants = {
  animate: { transition: { staggerChildren: 0.03 } },
};
```

- [ ] **Step 2: Typecheck**

Run: `npm run lint`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add src/lib/motion.ts
git commit -m "feat(ui): restrained motion presets"
```

---

## Task 5: Tooltip primitive (`ui/tooltip.tsx`)

**Files:**
- Create: `frontend/src/components/ui/tooltip.tsx`

- [ ] **Step 1: Create the file**

```tsx
import * as React from "react";
import { Tooltip as TooltipPrimitive } from "radix-ui";

import { cn } from "@/lib/utils";

function TooltipProvider({
  delayDuration = 200,
  ...props
}: React.ComponentProps<typeof TooltipPrimitive.Provider>) {
  return <TooltipPrimitive.Provider data-slot="tooltip-provider" delayDuration={delayDuration} {...props} />;
}

function Tooltip(props: React.ComponentProps<typeof TooltipPrimitive.Root>) {
  return <TooltipPrimitive.Root data-slot="tooltip" {...props} />;
}

function TooltipTrigger(props: React.ComponentProps<typeof TooltipPrimitive.Trigger>) {
  return <TooltipPrimitive.Trigger data-slot="tooltip-trigger" {...props} />;
}

function TooltipContent({
  className,
  sideOffset = 4,
  children,
  ...props
}: React.ComponentProps<typeof TooltipPrimitive.Content>) {
  return (
    <TooltipPrimitive.Portal>
      <TooltipPrimitive.Content
        data-slot="tooltip-content"
        sideOffset={sideOffset}
        className={cn(
          "z-50 overflow-hidden rounded-md border border-border bg-popover px-2.5 py-1.5 text-xs text-popover-foreground shadow-md data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:animate-in data-[state=open]:fade-in-0",
          className
        )}
        {...props}
      >
        {children}
      </TooltipPrimitive.Content>
    </TooltipPrimitive.Portal>
  );
}

export { Tooltip, TooltipTrigger, TooltipContent, TooltipProvider };
```

- [ ] **Step 2: Typecheck**

Run: `npm run lint`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add src/components/ui/tooltip.tsx
git commit -m "feat(ui): Tooltip primitive"
```

---

## Task 6: Popover primitive (`ui/popover.tsx`)

**Files:**
- Create: `frontend/src/components/ui/popover.tsx`

- [ ] **Step 1: Create the file**

```tsx
import * as React from "react";
import { Popover as PopoverPrimitive } from "radix-ui";

import { cn } from "@/lib/utils";

function Popover(props: React.ComponentProps<typeof PopoverPrimitive.Root>) {
  return <PopoverPrimitive.Root data-slot="popover" {...props} />;
}

function PopoverTrigger(props: React.ComponentProps<typeof PopoverPrimitive.Trigger>) {
  return <PopoverPrimitive.Trigger data-slot="popover-trigger" {...props} />;
}

function PopoverContent({
  className,
  align = "center",
  sideOffset = 4,
  ...props
}: React.ComponentProps<typeof PopoverPrimitive.Content>) {
  return (
    <PopoverPrimitive.Portal>
      <PopoverPrimitive.Content
        data-slot="popover-content"
        align={align}
        sideOffset={sideOffset}
        className={cn(
          "z-50 w-72 rounded-lg border border-border bg-popover p-3 text-popover-foreground shadow-md outline-none data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:animate-in data-[state=open]:fade-in-0",
          className
        )}
        {...props}
      />
    </PopoverPrimitive.Portal>
  );
}

export { Popover, PopoverTrigger, PopoverContent };
```

- [ ] **Step 2: Typecheck**

Run: `npm run lint`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add src/components/ui/popover.tsx
git commit -m "feat(ui): Popover primitive"
```

---

## Task 7: Drawer primitive (`ui/drawer.tsx`)

**Files:**
- Create: `frontend/src/components/ui/drawer.tsx`

Side-anchored Radix Dialog. Reuses the same `animate-in/animate-out` + slide utility names the existing `dialog.tsx` relies on.

- [ ] **Step 1: Create the file**

```tsx
import * as React from "react";
import { XIcon } from "lucide-react";
import { Dialog as DialogPrimitive } from "radix-ui";
import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "@/lib/utils";

const Drawer = (props: React.ComponentProps<typeof DialogPrimitive.Root>) => (
  <DialogPrimitive.Root data-slot="drawer" {...props} />
);
const DrawerTrigger = DialogPrimitive.Trigger;
const DrawerClose = DialogPrimitive.Close;

function DrawerOverlay({ className, ...props }: React.ComponentProps<typeof DialogPrimitive.Overlay>) {
  return (
    <DialogPrimitive.Overlay
      data-slot="drawer-overlay"
      className={cn(
        "fixed inset-0 z-50 bg-black/50 data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:animate-in data-[state=open]:fade-in-0",
        className
      )}
      {...props}
    />
  );
}

const drawerVariants = cva(
  "fixed z-50 flex flex-col bg-background shadow-lg data-[state=open]:animate-in data-[state=closed]:animate-out",
  {
    variants: {
      side: {
        right:
          "inset-y-0 right-0 h-full w-[40%] min-w-[360px] max-w-[560px] border-l data-[state=open]:slide-in-from-right data-[state=closed]:slide-out-to-right",
        left:
          "inset-y-0 left-0 h-full w-[40%] min-w-[360px] max-w-[560px] border-r data-[state=open]:slide-in-from-left data-[state=closed]:slide-out-to-left",
      },
    },
    defaultVariants: { side: "right" },
  }
);

function DrawerContent({
  className,
  children,
  side = "right",
  showCloseButton = true,
  ...props
}: React.ComponentProps<typeof DialogPrimitive.Content> &
  VariantProps<typeof drawerVariants> & { showCloseButton?: boolean }) {
  return (
    <DialogPrimitive.Portal>
      <DrawerOverlay />
      <DialogPrimitive.Content
        data-slot="drawer-content"
        className={cn(drawerVariants({ side }), className)}
        {...props}
      >
        {children}
        {showCloseButton && (
          <DialogPrimitive.Close className="absolute top-4 right-4 rounded-xs opacity-70 transition-opacity hover:opacity-100 focus:outline-none [&_svg]:size-4">
            <XIcon />
            <span className="sr-only">Close</span>
          </DialogPrimitive.Close>
        )}
      </DialogPrimitive.Content>
    </DialogPrimitive.Portal>
  );
}

function DrawerHeader({ className, ...props }: React.ComponentProps<"div">) {
  return <div data-slot="drawer-header" className={cn("flex flex-col gap-1 border-b border-border p-4", className)} {...props} />;
}

function DrawerBody({ className, ...props }: React.ComponentProps<"div">) {
  return <div data-slot="drawer-body" className={cn("flex-1 overflow-y-auto p-4", className)} {...props} />;
}

function DrawerFooter({ className, ...props }: React.ComponentProps<"div">) {
  return <div data-slot="drawer-footer" className={cn("flex justify-end gap-2 border-t border-border p-4", className)} {...props} />;
}

function DrawerTitle({ className, ...props }: React.ComponentProps<typeof DialogPrimitive.Title>) {
  return <DialogPrimitive.Title data-slot="drawer-title" className={cn("text-base font-semibold", className)} {...props} />;
}

function DrawerDescription({ className, ...props }: React.ComponentProps<typeof DialogPrimitive.Description>) {
  return <DialogPrimitive.Description data-slot="drawer-description" className={cn("text-sm text-muted-foreground", className)} {...props} />;
}

export {
  Drawer, DrawerTrigger, DrawerClose, DrawerContent,
  DrawerHeader, DrawerBody, DrawerFooter, DrawerTitle, DrawerDescription,
};
```

- [ ] **Step 2: Typecheck**

Run: `npm run lint`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add src/components/ui/drawer.tsx
git commit -m "feat(ui): side Drawer primitive"
```

> **Manual note for executor:** slide animation depends on `slide-in-from-right`/`slide-out-to-right` utilities (same animation plugin `dialog.tsx` already uses for `fade`/`zoom`). Confirm the drawer slides in Phase verify. If slide utilities are absent, replace the `slide-*` classes with `data-[state=open]:translate-x-0 data-[state=closed]:translate-x-full transition-transform duration-300` on the `right` variant (and the left mirror).

---

## Task 8: ConfirmDialog (`common/confirm-dialog.tsx`)

**Files:**
- Create: `frontend/src/components/common/confirm-dialog.tsx`

- [ ] **Step 1: Create the file**

```tsx
import * as React from "react";

import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

interface ConfirmDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description?: React.ReactNode;
  confirmLabel?: string;
  cancelLabel?: string;
  variant?: "default" | "destructive";
  /** When set, the user must type this exact string to enable the confirm button. */
  confirmPhrase?: string;
  onConfirm: () => void;
}

export function ConfirmDialog({
  open, onOpenChange, title, description,
  confirmLabel = "Confirm", cancelLabel = "Cancel",
  variant = "default", confirmPhrase, onConfirm,
}: ConfirmDialogProps) {
  const [typed, setTyped] = React.useState("");

  React.useEffect(() => {
    if (!open) setTyped("");
  }, [open]);

  const locked = confirmPhrase != null && typed !== confirmPhrase;

  function handleConfirm() {
    if (locked) return;
    onConfirm();
    onOpenChange(false);
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          {description && <DialogDescription>{description}</DialogDescription>}
        </DialogHeader>

        {confirmPhrase != null && (
          <div className="space-y-1.5">
            <Label htmlFor="confirm-phrase" className="text-xs text-muted-foreground">
              Type <span className="font-mono font-semibold text-foreground">{confirmPhrase}</span> to confirm
            </Label>
            <Input
              id="confirm-phrase"
              value={typed}
              autoFocus
              autoComplete="off"
              onChange={(e) => setTyped(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter") handleConfirm(); }}
            />
          </div>
        )}

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>{cancelLabel}</Button>
          <Button variant={variant} disabled={locked} onClick={handleConfirm}>{confirmLabel}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
```

- [ ] **Step 2: Typecheck**

Run: `npm run lint`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add src/components/common/confirm-dialog.tsx
git commit -m "feat(ui): ConfirmDialog with type-to-confirm mode"
```

---

## Task 9: ActionBar (`common/action-bar.tsx`)

**Files:**
- Create: `frontend/src/components/common/action-bar.tsx`

Status-driven instance lifecycle controls. Reversible actions (start/stop/pause/resume/restart) fire immediately with toast feedback — **no confirm**. Destroy uses `ConfirmDialog` type-to-confirm on the instance name.

- [ ] **Step 1: Create the file**

```tsx
import * as React from "react";
import { toast } from "sonner";
import { ExternalLink, Pause, Play, RotateCcw, Square, Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/common/confirm-dialog";
import { statusMeta } from "@/lib/status";
import { cn } from "@/lib/utils";
import {
  useDeleteInstance, usePauseInstance, useRestartInstance,
  useStartInstance, useStopInstance, useUnpauseInstance,
} from "@/hooks/use-instances";
import type { Instance } from "@/lib/types";

interface ActionBarProps {
  instance: Instance;
  size?: "sm" | "default";
  showConnect?: boolean;
  className?: string;
}

type SimpleMutation = { mutate: (id: string, opts?: { onError?: (e: Error) => void; onSuccess?: () => void }) => void };

export function ActionBar({ instance, size = "default", showConnect = true, className }: ActionBarProps) {
  const start = useStartInstance();
  const stop = useStopInstance();
  const restart = useRestartInstance();
  const pause = usePauseInstance();
  const unpause = useUnpauseInstance();
  const destroy = useDeleteInstance();
  const [confirmOpen, setConfirmOpen] = React.useState(false);

  const { group, label } = statusMeta(instance.status);
  const btn = size === "sm" ? "sm" : "default";

  function run(mut: SimpleMutation, verb: string) {
    return () => mut.mutate(instance.id, { onError: (e: Error) => toast.error(`${verb} failed: ${e.message}`) });
  }

  function doDestroy() {
    destroy.mutate(
      { id: instance.id, removeVolumes: false },
      {
        onError: (e: Error) => toast.error(`Destroy failed: ${e.message}`),
        onSuccess: () => toast.success(`Destroyed ${instance.name}`),
      }
    );
  }

  function connect() {
    window.open(`/i/${instance.subdomain}/`, "_blank");
  }

  return (
    <div className={cn("flex items-center gap-1.5", className)}>
      {group === "running" && (
        <>
          {showConnect && (
            <Button size={btn} onClick={connect}>
              <ExternalLink /> Connect
            </Button>
          )}
          <Button size={btn} variant="secondary" title="Restart" onClick={run(restart, "Restart")}>
            <RotateCcw />
          </Button>
          <Button size={btn} variant="secondary" title="Pause" onClick={run(pause, "Pause")}>
            <Pause />
          </Button>
          <Button size={btn} variant="secondary" title="Stop" onClick={run(stop, "Stop")}>
            <Square />
          </Button>
        </>
      )}

      {group === "paused" && (
        <>
          <Button size={btn} onClick={run(unpause, "Resume")}>
            <Play /> Resume
          </Button>
          <Button size={btn} variant="secondary" title="Stop" onClick={run(stop, "Stop")}>
            <Square />
          </Button>
        </>
      )}

      {(group === "stopped" || group === "error") && (
        <Button size={btn} onClick={run(start, "Start")}>
          <Play /> Start
        </Button>
      )}

      {group === "transition" && (
        <Button size={btn} variant="secondary" disabled>
          {label}…
        </Button>
      )}

      <Button
        size={btn}
        variant="ghost"
        className="text-destructive hover:text-destructive"
        title="Destroy"
        onClick={() => setConfirmOpen(true)}
      >
        <Trash2 />
      </Button>

      <ConfirmDialog
        open={confirmOpen}
        onOpenChange={setConfirmOpen}
        title={`Destroy "${instance.name}"?`}
        description="This permanently removes the container. Named volumes are kept."
        confirmLabel="Destroy"
        variant="destructive"
        confirmPhrase={instance.name}
        onConfirm={doDestroy}
      />
    </div>
  );
}
```

- [ ] **Step 2: Typecheck**

Run: `npm run lint`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add src/components/common/action-bar.tsx
git commit -m "feat(ui): status-driven ActionBar with destroy confirm"
```

---

## Task 10: StatTile + Gauge (`common/stat-tile.tsx`)

**Files:**
- Create: `frontend/src/components/common/stat-tile.tsx`

- [ ] **Step 1: Create the file**

```tsx
import * as React from "react";
import type { LucideIcon } from "lucide-react";

import { cn } from "@/lib/utils";

interface StatTileProps {
  icon?: LucideIcon;
  label: string;
  value: React.ReactNode;
  sub?: React.ReactNode;
  className?: string;
}

export function StatTile({ icon: Icon, label, value, sub, className }: StatTileProps) {
  return (
    <div className={cn("rounded-lg border border-border bg-card p-3", className)}>
      <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
        {Icon && <Icon className="size-3.5" />}
        {label}
      </div>
      <div className="mt-1 text-2xl font-semibold tabular-nums">{value}</div>
      {sub && <div className="mt-0.5 text-xs text-muted-foreground">{sub}</div>}
    </div>
  );
}

interface GaugeProps {
  value: number;
  max?: number;
  label?: string;
  /** CSS color string, e.g. a CHART_COLORS value. */
  color?: string;
  className?: string;
}

export function Gauge({ value, max = 100, label, color = "var(--chart-1)", className }: GaugeProps) {
  const pct = Math.min(100, Math.max(0, (value / max) * 100));
  return (
    <div className={cn("space-y-1", className)}>
      {label && (
        <div className="flex justify-between text-xs text-muted-foreground">
          <span>{label}</span>
          <span className="tabular-nums text-foreground">{Math.round(pct)}%</span>
        </div>
      )}
      <div className="h-2 w-full overflow-hidden rounded-full bg-secondary">
        <div className="h-full rounded-full transition-all duration-500" style={{ width: `${pct}%`, background: color }} />
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Typecheck**

Run: `npm run lint`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add src/components/common/stat-tile.tsx
git commit -m "feat(ui): StatTile and Gauge metric primitives"
```

---

## Task 11: DataTable (`common/data-table.tsx`)

**Files:**
- Create: `frontend/src/components/common/data-table.tsx`

- [ ] **Step 1: Create the file**

```tsx
import * as React from "react";

import { cn } from "@/lib/utils";

export interface Column<T> {
  key: string;
  header: React.ReactNode;
  render: (row: T) => React.ReactNode;
  className?: string;
  sortable?: boolean;
  sortValue?: (row: T) => string | number;
}

interface DataTableProps<T> {
  columns: Column<T>[];
  rows: T[];
  rowKey: (row: T) => string;
  onRowClick?: (row: T) => void;
  empty?: React.ReactNode;
  className?: string;
}

export function DataTable<T>({ columns, rows, rowKey, onRowClick, empty, className }: DataTableProps<T>) {
  const [sort, setSort] = React.useState<{ key: string; dir: 1 | -1 } | null>(null);

  const sorted = React.useMemo(() => {
    if (!sort) return rows;
    const col = columns.find((c) => c.key === sort.key);
    if (!col?.sortValue) return rows;
    const get = col.sortValue;
    return [...rows].sort((a, b) => {
      const av = get(a);
      const bv = get(b);
      return av < bv ? -sort.dir : av > bv ? sort.dir : 0;
    });
  }, [rows, sort, columns]);

  function toggleSort(key: string) {
    setSort((s) => (s?.key === key ? { key, dir: s.dir === 1 ? -1 : 1 } : { key, dir: 1 }));
  }

  if (rows.length === 0 && empty) {
    return <div className="py-8 text-center text-sm text-muted-foreground">{empty}</div>;
  }

  return (
    <div className={cn("overflow-x-auto rounded-lg border border-border", className)}>
      <table className="w-full text-sm">
        <thead className="border-b border-border bg-secondary/40 text-xs text-muted-foreground">
          <tr>
            {columns.map((c) => (
              <th
                key={c.key}
                className={cn(
                  "px-3 py-2 text-left font-medium",
                  c.sortable && "cursor-pointer select-none hover:text-foreground",
                  c.className
                )}
                onClick={c.sortable ? () => toggleSort(c.key) : undefined}
              >
                {c.header}
                {sort?.key === c.key ? (sort.dir === 1 ? " ↑" : " ↓") : ""}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {sorted.map((row) => (
            <tr
              key={rowKey(row)}
              onClick={onRowClick ? () => onRowClick(row) : undefined}
              className={cn("border-b border-border/60 last:border-0", onRowClick && "cursor-pointer hover:bg-secondary/40")}
            >
              {columns.map((c) => (
                <td key={c.key} className={cn("px-3 py-2", c.className)}>
                  {c.render(row)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
```

- [ ] **Step 2: Typecheck**

Run: `npm run lint`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add src/components/common/data-table.tsx
git commit -m "feat(ui): compact sortable DataTable"
```

---

## Task 12: SearchSortBar (`common/search-sort-bar.tsx`)

**Files:**
- Create: `frontend/src/components/common/search-sort-bar.tsx`

- [ ] **Step 1: Create the file**

```tsx
import * as React from "react";
import { Search } from "lucide-react";

import { cn } from "@/lib/utils";
import { Input } from "@/components/ui/input";

interface SortOption {
  value: string;
  label: string;
}

interface SearchSortBarProps {
  query: string;
  onQueryChange: (q: string) => void;
  placeholder?: string;
  sortOptions?: SortOption[];
  sortBy?: string;
  onSortChange?: (v: string) => void;
  /** Extra filter controls or action buttons rendered at the end. */
  children?: React.ReactNode;
  className?: string;
}

export function SearchSortBar({
  query, onQueryChange, placeholder = "Search…",
  sortOptions, sortBy, onSortChange, children, className,
}: SearchSortBarProps) {
  return (
    <div className={cn("flex flex-wrap items-center gap-2", className)}>
      <div className="relative min-w-48 flex-1">
        <Search className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground" />
        <Input value={query} onChange={(e) => onQueryChange(e.target.value)} placeholder={placeholder} className="pl-8" />
      </div>
      {sortOptions && onSortChange && (
        <select
          value={sortBy}
          onChange={(e) => onSortChange(e.target.value)}
          className="h-9 rounded-md border border-input bg-background px-2 text-sm outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50"
        >
          {sortOptions.map((o) => (
            <option key={o.value} value={o.value}>{o.label}</option>
          ))}
        </select>
      )}
      {children}
    </div>
  );
}
```

- [ ] **Step 2: Typecheck**

Run: `npm run lint`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add src/components/common/search-sort-bar.tsx
git commit -m "feat(ui): shared SearchSortBar control"
```

---

## Task 13: Refactor status-badge to use `status.ts`

**Files:**
- Modify: `frontend/src/components/instances/status-badge.tsx` (full rewrite, 23 → ~16 lines)

- [ ] **Step 1: Replace the file contents**

```tsx
import { cn } from "@/lib/utils";
import { statusMeta } from "@/lib/status";

export function StatusBadge({ status, showIcon = false }: { status: string; showIcon?: boolean }) {
  const m = statusMeta(status);
  const Icon = m.icon;
  return (
    <span className={cn("flex items-center gap-1.5 text-xs font-medium", m.textClass)}>
      {showIcon ? (
        <Icon className={cn("size-3", m.pulse && "animate-pulse")} />
      ) : (
        <span className={cn("h-1.5 w-1.5 rounded-full", m.dotClass, m.pulse && "animate-pulse")} />
      )}
      {m.label}
    </span>
  );
}
```

- [ ] **Step 2: Typecheck**

Run: `npm run lint`
Expected: PASS (StatusBadge is imported by instance components; the prop shape `{ status }` is unchanged, the new optional `showIcon` is additive).

- [ ] **Step 3: Commit**

```bash
git add src/components/instances/status-badge.tsx
git commit -m "refactor(ui): status-badge consumes status metadata, removes hardcoded amber"
```

---

## Task 14: Refactor sparkline to drop hardcoded gridline color

**Files:**
- Modify: `frontend/src/components/instances/sparkline.tsx:58`

Only the hardcoded gridline `stroke="#666"` is changed here; series colors are passed by callers and will be switched to `CHART_COLORS` in the per-area plans.

- [ ] **Step 1: Replace the gridline stroke**

Find (line ~58):

```tsx
          <line x1={0} y1={height / 2} x2={w} y2={height / 2} stroke="#666" strokeWidth={0.5} opacity={0.2} strokeDasharray="2 3" />
```

Replace `stroke="#666"` with `stroke="var(--muted-foreground)"`:

```tsx
          <line x1={0} y1={height / 2} x2={w} y2={height / 2} stroke="var(--muted-foreground)" strokeWidth={0.5} opacity={0.2} strokeDasharray="2 3" />
```

- [ ] **Step 2: Typecheck**

Run: `npm run lint`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add src/components/instances/sparkline.tsx
git commit -m "refactor(ui): sparkline gridline uses token color"
```

---

## Task 15: Mount TooltipProvider in App

**Files:**
- Modify: `frontend/src/App.tsx`

Tooltips require a provider above any `<Tooltip>`. Wrap the app's root element.

- [ ] **Step 1: Add the import**

At the top of `App.tsx`, with the other imports:

```tsx
import { TooltipProvider } from "@/components/ui/tooltip";
```

- [ ] **Step 2: Wrap the root**

Change the outermost element from:

```tsx
  return (
    <div className="flex min-h-screen flex-col bg-background">
```

to wrap it in the provider:

```tsx
  return (
    <TooltipProvider>
    <div className="flex min-h-screen flex-col bg-background">
```

and add the matching closing tag — change the final:

```tsx
    </div>
  );
}
```

to:

```tsx
    </div>
    </TooltipProvider>
  );
}
```

- [ ] **Step 3: Typecheck**

Run: `npm run lint`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add src/App.tsx
git commit -m "feat(ui): mount TooltipProvider at app root"
```

---

## Phase Verification

- [ ] **Step 1: Full build**

Run: `npm run build`
Expected: PASS — `tsc -b` reports no errors, `vite build` completes and writes `dist/`.

- [ ] **Step 2: Manual smoke (dev server)**

Run: `npm run dev`, open the app.
Verify:
- App loads, no console errors.
- Theme toggle (light/dark/system) still works; status colors render in both themes.
- Status badges show correct label/color for at least running + stopped instances (no visual regression).

- [ ] **Step 3: Confirm no new runtime deps**

Run: `git diff HEAD~15 -- package.json` (or inspect `package.json`)
Expected: `dependencies` unchanged (only new source files added).

---

## Self-Review (completed by plan author)

- **Spec coverage:** Foundation (status.ts, chart.ts, motion.ts, globals tokens) → Tasks 1–4. Primitives (ConfirmDialog, Tooltip, Popover, Drawer, ActionBar, StatTile/Gauge, DataTable, SearchSortBar, Sparkline) → Tasks 5–14. TooltipProvider wiring → Task 15. Per-area refactors are explicitly deferred to Plans 2–5.
- **Placeholder scan:** none — every step has full code or exact edit.
- **Type consistency:** `statusMeta()` / `StatusMeta.group` used identically in status-badge (Task 13) and ActionBar (Task 9). `CHART_COLORS` (Task 3) consumed by Gauge default (Task 10) and deferred sparkline callers. Delete signature `{ id, removeVolumes }` (Task 9) matches `useDeleteInstance` in `use-instances.ts`. Status union in `status.ts` matches `Instance.status` in `types.ts` exactly (10 values incl. `created`).
- **Known risk flagged:** Drawer slide utilities (Task 7 manual note).

## Deferred to later plans (NOT in this plan)
- Plan 2 — Instances: card/card-sm/row/grid/detail consume ActionBar+status+Drawer; decompose instance-card, instance-grid, instance-detail; switch sparkline callers to CHART_COLORS.
- Plan 3 — Templates+Registry: decompose launch-modal; registry-browser SearchSortBar + detail Drawer.
- Plan 4 — System: metrics tabs consume StatTile/Gauge/DataTable; replace remaining confirm() calls.
- Plan 5 — Shell: header/tab-nav density, tooltip chips.
