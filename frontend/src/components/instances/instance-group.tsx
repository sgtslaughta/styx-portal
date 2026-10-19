import { useCallback, useMemo, useState } from "react";
import { CheckSquare, Filter, Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useInstances } from "@/hooks/use-instances";
import { useTemplates } from "@/hooks/use-templates";
import { useInstanceConnect } from "@/hooks/use-instance-connect";
import { isRunning, statusMeta } from "@/lib/status";
import { instLine, type Selection } from "@/lib/workspace";
import { cn } from "@/lib/utils";
import type { Instance } from "@/lib/types";
import { InstanceBulkBar } from "./instance-bulk-bar";
import { EmptyLine, GroupHeader, TemplateIcon, WorkspaceRow, useCollapsed } from "./workspace-row";

type StatusFilter = "all" | "running" | "stopped" | "paused";
const FILTERS: StatusFilter[] = ["all", "running", "stopped", "paused"];
const FILTER_LABELS: Record<StatusFilter, string> = { all: "All", running: "Running", stopped: "Stopped", paused: "Paused" };
const ORDER: Record<string, number> = {
  running: 0, idle: 1, pulling: 2, starting: 3, creating: 4, paused: 5, stopping: 6, stopped: 7, error: 8, created: 9,
};
const COUNTS = [
  { label: "running", dot: "bg-success", match: (s: string) => s === "running" || s === "idle" },
  { label: "paused", dot: "bg-warning", match: (s: string) => s === "paused" },
  { label: "stopped", dot: "bg-muted-foreground", match: (s: string) => s === "stopped" },
  { label: "error", dot: "bg-destructive", match: (s: string) => s === "error" },
];
const LIST_ID = "home-instances";

function byFilter(i: Instance, f: StatusFilter): boolean {
  if (f === "running") return isRunning(i.status);
  if (f === "paused") return i.status === "paused";
  if (f === "stopped") return i.status === "stopped" || i.status === "error";
  return true;
}

export function InstanceGroup({ query, selection, onSelect, onLaunch }: {
  query: string; selection: Selection | null; onSelect: (s: Selection) => void; onLaunch: () => void;
}) {
  const { data: instances, isError, refetch } = useInstances();
  const { data: templates } = useTemplates();
  const connect = useInstanceConnect();
  const [collapsed, toggle] = useCollapsed("instances");
  const [filter, setFilter] = useState<StatusFilter>("all");
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const tmpl = useCallback((i: Instance) => templates?.find((t) => t.id === i.template_id), [templates]);

  const all = useMemo(() => instances ?? [], [instances]);
  const rows = useMemo(() => {
    const q = query.trim().toLowerCase();
    return all
      .filter((i) => byFilter(i, filter))
      .filter((i) => !q || `${i.name} ${i.subdomain} ${tmpl(i)?.image ?? ""}`.toLowerCase().includes(q))
      .sort((a, b) => (ORDER[a.status] ?? 9) - (ORDER[b.status] ?? 9) || a.name.localeCompare(b.name));
  }, [all, query, filter, tmpl]);

  const selecting = picked.size > 0;
  const togglePick = (id: string) => setPicked((p) => {
    const n = new Set(p);
    if (n.has(id)) n.delete(id); else n.add(id);
    return n;
  });

  return (
    <section aria-label="Instances" className="mt-2">
      <GroupHeader title="Instances" count={all.length} collapsed={collapsed} onToggle={toggle} controlsId={LIST_ID}>
        <span className="flex items-center gap-2 text-xs text-muted-foreground max-sm:hidden">
          {COUNTS.map((c) => {
            const n = all.filter((i) => c.match(i.status)).length;
            return n ? (
              <span key={c.label} className="flex items-center gap-1" title={`${n} ${c.label}`}>
                <span className={cn("size-1.5 rounded-full", c.dot)} aria-hidden />
                <span className="tabular-nums text-foreground">{n}</span>
                <span className="sr-only">{c.label}</span>
              </span>
            ) : null;
          })}
        </span>
        <Button size="sm" variant="ghost" title="Filter by status" className="max-sm:size-11 max-sm:px-0"
          onClick={() => setFilter((f) => FILTERS[(FILTERS.indexOf(f) + 1) % FILTERS.length]!)}>
          <Filter aria-hidden /><span className="max-sm:sr-only">{FILTER_LABELS[filter]}</span>
        </Button>
        <Button size="sm" variant={selecting ? "secondary" : "ghost"} className="max-sm:h-11 max-sm:min-w-11 max-sm:px-2"
          onClick={() => setPicked(selecting ? new Set() : new Set(rows.map((i) => i.id)))}>
          <CheckSquare aria-hidden /><span className={selecting ? undefined : "max-sm:sr-only"}>{selecting ? `${picked.size} selected` : "Select"}</span>
        </Button>
        <Button size="sm" onClick={onLaunch} className="max-sm:size-11 max-sm:px-0"><Plus aria-hidden /><span className="max-sm:sr-only">Launch</span></Button>
      </GroupHeader>
      {!collapsed && (
        <div id={LIST_ID} className="py-1">
          {isError ? (
            <div className="flex flex-wrap items-center gap-2 px-2 py-3 text-sm text-muted-foreground">
              <span>Backend unavailable — retrying…</span>
              <Button size="sm" variant="secondary" onClick={() => void refetch()}>Retry now</Button>
            </div>
          ) : !instances ? (
            <div className="h-12 animate-pulse rounded-lg bg-muted" />
          ) : all.length === 0 ? (
            <EmptyLine text="No instances yet." action={{ label: "Launch an instance", onClick: onLaunch }} />
          ) : rows.length === 0 ? (
            <p className="px-2 py-2 text-xs text-muted-foreground">No instances match.</p>
          ) : (
            <ul className="space-y-0.5">
              {rows.map((i) => {
                const m = statusMeta(i.status);
                return (
                  <WorkspaceRow
                    key={i.id}
                    icon={<TemplateIcon icon={tmpl(i)?.icon ?? null} />}
                    name={i.name}
                    line={instLine(i)}
                    dot={{ dotClass: cn(m.dotClass, m.pulse && "animate-pulse"), label: m.label }}
                    dim={m.group === "stopped" || m.group === "error"}
                    selected={selection?.kind === "instance" && selection.id === i.id}
                    onSelect={() => (selecting ? togglePick(i.id) : onSelect({ kind: "instance", id: i.id }))}
                    quick={isRunning(i.status) && !selecting ? { label: `Connect to ${i.name}`, onClick: () => connect(i) } : undefined}
                    leading={
                      <input type="checkbox" aria-label={`Select ${i.name}`} checked={picked.has(i.id)} onChange={() => togglePick(i.id)}
                        className={cn("size-4 shrink-0 accent-primary",
                          !selecting && "opacity-0 group-hover:opacity-100 focus-visible:opacity-100 pointer-coarse:hidden")} />
                    }
                  />
                );
              })}
            </ul>
          )}
        </div>
      )}
      <InstanceBulkBar selected={all.filter((i) => picked.has(i.id))} onClear={() => setPicked(new Set())} />
    </section>
  );
}
