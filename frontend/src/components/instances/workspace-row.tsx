import { useState, type ReactNode } from "react";
import { ChevronDown, ExternalLink } from "lucide-react";
import { Button } from "@/components/ui/button";
import { readLocal, writeLocal } from "@/lib/local";
import { cn } from "@/lib/utils";

/** Collapsed state of a home group, remembered per browser. */
export function useCollapsed(group: string): [boolean, () => void] {
  const key = `styx.home.collapsed.${group}`;
  const [collapsed, setCollapsed] = useState(() => readLocal(key) === "1");
  const toggle = () => {
    const next = !collapsed;
    setCollapsed(next);
    writeLocal(key, next ? "1" : null);
  };
  return [collapsed, toggle];
}

/** Sticky, collapsible group header. `children` are the group's controls (outside the toggle). */
export function GroupHeader({ title, count, collapsed, onToggle, controlsId, children }: {
  title: string; count: number; collapsed: boolean; onToggle: () => void; controlsId: string; children?: ReactNode;
}) {
  return (
    <div className="sticky top-0 z-10 flex min-h-11 flex-wrap items-center gap-2 border-b border-border bg-background/95 px-1 py-1 backdrop-blur">
      <button type="button" onClick={onToggle} aria-expanded={!collapsed} aria-controls={controlsId}
        className="mr-auto inline-flex min-h-9 items-center gap-1.5 rounded-md px-1 text-sm font-medium text-muted-foreground outline-none hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring max-sm:min-h-11">
        <ChevronDown className={cn("size-4 transition-transform", collapsed && "-rotate-90")} aria-hidden />
        {title} · <span className="tabular-nums">{count}</span>
      </button>
      {children}
    </div>
  );
}

/** One row look for both kinds: icon, name, one secondary line, status dot, hover/focus quick-connect. */
export function WorkspaceRow({ icon, name, line, dot, selected, dim, onSelect, quick, leading }: {
  icon: ReactNode; name: string; line: string; dot: { dotClass: string; label: string };
  selected?: boolean; dim?: boolean; onSelect: () => void;
  /** One-click open; omitted when the workspace can't be opened right now. */
  quick?: { label: string; onClick: () => void };
  leading?: ReactNode;
}) {
  return (
    <li className={cn("group relative flex items-center gap-2 rounded-lg px-2 hover:bg-muted/50", selected && "bg-primary/10 ring-1 ring-primary/40")}>
      {leading}
      <button type="button" onClick={onSelect} aria-current={selected ? "true" : undefined}
        className="flex min-h-12 min-w-0 flex-1 items-center gap-3 rounded-md py-1.5 text-left outline-none focus-visible:ring-2 focus-visible:ring-ring">
        <span className={cn("flex size-8 shrink-0 items-center justify-center", dim && "opacity-50 grayscale")}>{icon}</span>
        <span className="min-w-0 flex-1">
          <span className="block truncate text-sm font-medium">{name}</span>
          <span className="block truncate text-xs text-muted-foreground">{line}</span>
        </span>
        <span className={cn("size-2.5 shrink-0 rounded-full", dot.dotClass)} title={dot.label} aria-hidden />
        <span className="sr-only">{dot.label}</span>
      </button>
      {quick && (
        <button type="button" onClick={quick.onClick} aria-label={quick.label} title={quick.label}
          className="inline-flex size-9 shrink-0 items-center justify-center rounded-md text-muted-foreground opacity-0 outline-none hover:bg-secondary hover:text-foreground focus-visible:opacity-100 focus-visible:ring-2 focus-visible:ring-ring group-hover:opacity-100 max-sm:size-11 pointer-coarse:size-11 pointer-coarse:opacity-100">
          <ExternalLink className="size-4" aria-hidden />
        </button>
      )}
    </li>
  );
}

/** Empty group: one line + optional action. */
export function EmptyLine({ text, action }: { text: string; action?: { label: string; onClick: () => void } }) {
  return (
    <div className="flex flex-wrap items-center gap-2 px-2 py-3 text-sm text-muted-foreground">
      <span>{text}</span>
      {action && <Button size="sm" variant="outline" onClick={action.onClick}>{action.label}</Button>}
    </div>
  );
}
