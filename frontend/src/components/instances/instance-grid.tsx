import { useState, useMemo, useCallback } from "react";
import { motion, AnimatePresence, useReducedMotion } from "framer-motion";
import { LayoutGrid, List, Maximize2, Filter, Play, Square, Pause, Trash2, CheckSquare, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { SearchSortBar } from "@/components/common/search-sort-bar";
import { ConfirmDialog } from "@/components/common/confirm-dialog";
import { useInstances, useStartInstance, useStopInstance, usePauseInstance, useUnpauseInstance, useDeleteInstance } from "@/hooks/use-instances";
import { useTemplates } from "@/hooks/use-templates";
import { InstanceCard } from "./instance-card";
import { InstanceCardSm } from "./instance-card-sm";
import { InstanceRow } from "./instance-row";
import { toast } from "sonner";
import { shortError } from "@/lib/utils";
import type { Instance } from "@/lib/types";

type ViewMode = "compact" | "normal" | "large";
type SortKey = "name" | "status" | "created" | "uptime";
type StatusFilter = "all" | "running" | "stopped" | "paused";

interface InstanceGridProps {
  onSelect: (instance: Instance) => void;
  onLaunch: () => void;
  selectedId?: string;
  dense?: boolean;
}

const STATUS_ORDER: Record<string, number> = {
  running: 0, idle: 1, pulling: 2, starting: 3, creating: 4, paused: 5, stopping: 6, stopped: 7, error: 8, created: 9,
};

function sortInstances(instances: Instance[], key: SortKey): Instance[] {
  const sorted = [...instances];
  switch (key) {
    case "name":
      return sorted.sort((a, b) => a.name.localeCompare(b.name));
    case "status":
      return sorted.sort((a, b) => (STATUS_ORDER[a.status] ?? 9) - (STATUS_ORDER[b.status] ?? 9));
    case "created":
      return sorted.sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime());
    case "uptime":
      return sorted.sort((a, b) => {
        const aUp = a.started_at ? new Date(a.started_at + "Z").getTime() : 0;
        const bUp = b.started_at ? new Date(b.started_at + "Z").getTime() : 0;
        return aUp - bUp;
      });
  }
}

function filterByStatus(instances: Instance[], filter: StatusFilter): Instance[] {
  if (filter === "all") return instances;
  if (filter === "running") return instances.filter((i) => i.status === "running" || i.status === "idle");
  if (filter === "paused") return instances.filter((i) => i.status === "paused");
  return instances.filter((i) => i.status === "stopped" || i.status === "error");
}

const VIEW_ICONS: Record<ViewMode, typeof List> = { compact: List, normal: LayoutGrid, large: Maximize2 };
const VIEW_CYCLE: ViewMode[] = ["compact", "normal", "large"];
const SORT_LABELS: Record<SortKey, string> = { name: "Name", status: "Status", created: "Created", uptime: "Uptime" };
const SORT_CYCLE: SortKey[] = ["status", "name", "created", "uptime"];
const FILTER_LABELS: Record<StatusFilter, string> = { all: "All", running: "Running", stopped: "Stopped", paused: "Paused" };
const FILTER_CYCLE: StatusFilter[] = ["all", "running", "stopped", "paused"];

export function InstanceGrid({ onSelect, onLaunch, selectedId, dense = false }: InstanceGridProps) {
  const { data: instances, isLoading, isError, refetch } = useInstances();
  const { data: templates } = useTemplates();
  const reduce = useReducedMotion();

  const [view, setView] = useState<ViewMode>(dense ? "compact" : "normal");
  const [sort, setSort] = useState<SortKey>("status");
  const [filter, setFilter] = useState<StatusFilter>("all");
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [bulkConfirm, setBulkConfirm] = useState(false);

  const startMut = useStartInstance();
  const stopMut = useStopInstance();
  const pauseMut = usePauseInstance();
  const unpauseMut = useUnpauseInstance();
  const destroyMut = useDeleteInstance();

  const bulkBusy = startMut.isPending || stopMut.isPending || pauseMut.isPending || unpauseMut.isPending || destroyMut.isPending;

  const processed = useMemo(() => {
    if (!instances) return [];
    let result = instances;
    if (search) {
      const q = search.toLowerCase();
      result = result.filter((i) => i.name.toLowerCase().includes(q) || i.subdomain.toLowerCase().includes(q));
    }
    result = filterByStatus(result, filter);
    return sortInstances(result, sort);
  }, [instances, search, filter, sort]);

  const toggleSelect = useCallback((id: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  }, []);

  const selectAll = useCallback(() => {
    setSelected(new Set(processed.map((i) => i.id)));
  }, [processed]);

  const clearSelection = useCallback(() => setSelected(new Set()), []);

  const selectedInstances = useMemo(
    () => (instances ?? []).filter((i) => selected.has(i.id)),
    [instances, selected]
  );

  const selRunning = selectedInstances.filter((i) => i.status === "running" || i.status === "idle");
  const selStopped = selectedInstances.filter((i) => i.status === "stopped" || i.status === "error");
  const selPaused = selectedInstances.filter((i) => i.status === "paused");

  function bulkStart() {
    selStopped.forEach((i) => startMut.mutate(i.id, { onError: (e) => { console.error(i.name, e); toast.error(shortError(`${i.name}: ${e.message}`)); } }));
    toast.success(`Starting ${selStopped.length} instance(s)`);
    clearSelection();
  }
  function bulkStop() {
    [...selRunning, ...selPaused].forEach((i) => stopMut.mutate(i.id, { onError: (e) => { console.error(i.name, e); toast.error(shortError(`${i.name}: ${e.message}`)); } }));
    toast.success(`Stopping ${selRunning.length + selPaused.length} instance(s)`);
    clearSelection();
  }
  function bulkPause() {
    selRunning.forEach((i) => pauseMut.mutate(i.id, { onError: (e) => { console.error(i.name, e); toast.error(shortError(`${i.name}: ${e.message}`)); } }));
    toast.success(`Pausing ${selRunning.length} instance(s)`);
    clearSelection();
  }
  function bulkUnpause() {
    selPaused.forEach((i) => unpauseMut.mutate(i.id, { onError: (e) => { console.error(i.name, e); toast.error(shortError(`${i.name}: ${e.message}`)); } }));
    toast.success(`Resuming ${selPaused.length} instance(s)`);
    clearSelection();
  }
  function runBulkDestroy() {
    selectedInstances.forEach((i) => destroyMut.mutate({ id: i.id, removeVolumes: false }, { onError: (e) => { console.error(i.name, e); toast.error(shortError(`${i.name}: ${e.message}`)); } }));
    toast.success(`Destroying ${selected.size} instance(s)`);
    clearSelection();
  }

  function bulkDestroy() {
    setBulkConfirm(true);
  }

  function cycleView() { setView((v) => VIEW_CYCLE[(VIEW_CYCLE.indexOf(v) + 1) % VIEW_CYCLE.length]!); }
  function cycleSort() { setSort((s) => SORT_CYCLE[(SORT_CYCLE.indexOf(s) + 1) % SORT_CYCLE.length]!); }
  function cycleFilter() { setFilter((f) => FILTER_CYCLE[(FILTER_CYCLE.indexOf(f) + 1) % FILTER_CYCLE.length]!); }

  const ViewIcon = VIEW_ICONS[view];
  const hasSelection = selected.size > 0;

  if (isLoading) {
    return (
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
        {[1, 2, 3].map((i) => (
          <div key={i} className="aspect-[4/3] rounded-xl bg-card animate-pulse" />
        ))}
      </div>
    );
  }

  if (isError) {
    return (
      <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="flex flex-col items-center gap-3 py-12 text-center text-sm text-muted-foreground">
        <span>Backend unavailable — retrying…</span>
        <Button size="sm" variant="secondary" onClick={() => refetch()}>Retry now</Button>
      </motion.div>
    );
  }

  if (!instances?.length) {
    return (
      <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ type: "spring", stiffness: 300, damping: 25 }} className="flex flex-col items-center justify-center py-20 text-center">
        <p className="mb-1 text-lg font-medium text-foreground">No instances yet</p>
        <p className="mb-4 text-sm text-muted-foreground">Browse the Template Gallery to launch one.</p>
        <button onClick={onLaunch} className="text-sm font-medium text-primary hover:underline">Go to Template Gallery &rarr;</button>
      </motion.div>
    );
  }

  const gridClass = view === "compact"
    ? "flex flex-col gap-1.5"
    : view === "large"
      ? "grid grid-cols-1 gap-5 md:grid-cols-2"
      : "grid grid-cols-1 gap-3 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4";

  return (
    <div className="space-y-3">
      {/* Toolbar */}
      <SearchSortBar
        query={search}
        onQueryChange={setSearch}
        placeholder="Search instances…"
      >
        {/* Select all / clear */}
        <button
          onClick={hasSelection ? clearSelection : selectAll}
          className={`inline-flex items-center gap-1.5 rounded-md border px-2.5 h-8 text-xs transition-colors ${
            hasSelection ? "border-primary/50 bg-primary/10 text-primary hover:bg-primary/20" : "border-border bg-card text-muted-foreground hover:text-foreground hover:border-primary/40"
          }`}
          title={hasSelection ? "Clear selection" : "Select all"}
        >
          <CheckSquare className="h-3.5 w-3.5" />
          {hasSelection ? `${selected.size} selected` : "Select"}
        </button>

        <button onClick={cycleFilter} className="inline-flex items-center gap-1.5 rounded-md border border-border bg-card px-2.5 h-8 text-xs text-muted-foreground hover:text-foreground hover:border-primary/40 transition-colors" title="Filter by status">
          <Filter className="h-3.5 w-3.5" />
          <span>{FILTER_LABELS[filter]}</span>
        </button>

        <button onClick={cycleSort} className="inline-flex items-center gap-1.5 rounded-md border border-border bg-card px-2.5 h-8 text-xs text-muted-foreground hover:text-foreground hover:border-primary/40 transition-colors" title="Sort by">
          <span>{SORT_LABELS[sort]}</span>
        </button>

        {!dense && (
          <button onClick={cycleView} className="inline-flex items-center gap-1.5 rounded-md border border-border bg-card px-2.5 h-8 text-xs text-muted-foreground hover:text-foreground hover:border-primary/40 transition-colors" title={`View: ${view}`}>
            <ViewIcon className="h-3.5 w-3.5" />
            <span className="capitalize">{view}</span>
          </button>
        )}

        <span className="text-[10px] text-muted-foreground tabular-nums">
          {processed.length}/{instances.length}
        </span>
      </SearchSortBar>

      {/* Grid / List */}
      {processed.length === 0 ? (
        <p className="py-8 text-center text-sm text-muted-foreground">No instances match.</p>
      ) : (
        <motion.div layout className={gridClass}>
          <AnimatePresence mode="popLayout">
            {processed.map((instance) => {
              const tmplIcon = templates?.find((t) => t.id === instance.template_id)?.icon ?? null;
              const isSelected = selected.has(instance.id);
              return (
                <SelectableWrapper
                  key={instance.id}
                  id={instance.id}
                  isSelected={isSelected}
                  isHighlighted={selectedId === instance.id}
                  selectionActive={hasSelection}
                  onToggle={toggleSelect}
                  view={view}
                >
                  {view === "compact" ? (
                    <InstanceRow instance={instance} icon={tmplIcon} onSelect={hasSelection ? () => toggleSelect(instance.id) : onSelect} />
                  ) : view === "normal" ? (
                    <InstanceCardSm instance={instance} icon={tmplIcon} onSelect={hasSelection ? () => toggleSelect(instance.id) : onSelect} />
                  ) : (
                    <InstanceCard instance={instance} icon={tmplIcon} onSelect={hasSelection ? () => toggleSelect(instance.id) : onSelect} />
                  )}
                </SelectableWrapper>
              );
            })}
          </AnimatePresence>
        </motion.div>
      )}

      {/* Bulk action bar */}
      <AnimatePresence>
        {hasSelection && (
          <motion.div
            initial={reduce ? undefined : { y: 60, opacity: 0 }}
            animate={reduce ? undefined : { y: 0, opacity: 1 }}
            exit={reduce ? undefined : { y: 60, opacity: 0 }}
            transition={{ type: "spring", stiffness: 400, damping: 30 }}
            className="fixed bottom-4 left-1/2 -translate-x-1/2 z-50 flex items-center gap-2 rounded-xl border border-border bg-card px-4 py-2.5 shadow-2xl"
          >
            <span className="text-xs font-medium text-foreground mr-1">{selected.size} selected</span>

            {selStopped.length > 0 && (
              <Button size="sm" variant="secondary" onClick={bulkStart} disabled={bulkBusy} className="h-7 text-xs gap-1">
                <Play className="h-3 w-3" /> Start {selStopped.length}
              </Button>
            )}
            {selRunning.length > 0 && (
              <Button size="sm" variant="secondary" onClick={bulkPause} disabled={bulkBusy} className="h-7 text-xs gap-1">
                <Pause className="h-3 w-3" /> Pause {selRunning.length}
              </Button>
            )}
            {selPaused.length > 0 && (
              <Button size="sm" variant="secondary" onClick={bulkUnpause} disabled={bulkBusy} className="h-7 text-xs gap-1">
                <Play className="h-3 w-3" /> Resume {selPaused.length}
              </Button>
            )}
            {(selRunning.length + selPaused.length) > 0 && (
              <Button size="sm" variant="secondary" onClick={bulkStop} disabled={bulkBusy} className="h-7 text-xs gap-1">
                <Square className="h-3 w-3" /> Stop {selRunning.length + selPaused.length}
              </Button>
            )}
            <Button size="sm" variant="ghost" className="text-destructive hover:text-destructive h-7 text-xs gap-1" onClick={bulkDestroy} disabled={bulkBusy}>
              <Trash2 className="h-3 w-3" /> Destroy
            </Button>

            <div className="w-px h-5 bg-border mx-1" />
            <button onClick={clearSelection} className="rounded-md p-1 text-muted-foreground hover:text-foreground transition-colors" title="Clear selection" aria-label="Clear selection">
              <X className="h-4 w-4" />
            </button>
          </motion.div>
        )}
      </AnimatePresence>

      <ConfirmDialog
        open={bulkConfirm}
        onOpenChange={setBulkConfirm}
        title={`Destroy ${selected.size} instance(s)?`}
        description="Containers will be removed. Named volumes are kept."
        confirmLabel="Destroy"
        variant="destructive"
        confirmPhrase="destroy"
        onConfirm={runBulkDestroy}
      />
    </div>
  );
}

interface SelectableWrapperProps {
  id: string;
  isSelected: boolean;
  isHighlighted?: boolean;
  selectionActive: boolean;
  onToggle: (id: string) => void;
  view: ViewMode;
  children: React.ReactNode;
}

function SelectableWrapper({ id, isSelected, isHighlighted, selectionActive, onToggle, view, children }: SelectableWrapperProps) {
  return (
    <div className={`relative ${isSelected ? "ring-2 ring-primary/60 rounded-xl" : ""} ${isHighlighted && !isSelected ? "ring-2 ring-primary/40 rounded-xl" : ""}`}>
      {/* Checkbox overlay */}
      <div
        className={`absolute z-10 transition-opacity ${
          view === "compact" ? "top-1/2 -translate-y-1/2 left-1" : "top-2 left-2"
        } ${selectionActive ? "opacity-100" : "opacity-0 group-hover:opacity-100"}`}
      >
        <button
          onClick={(e) => { e.stopPropagation(); onToggle(id); }}
          className={`h-5 w-5 rounded border-2 flex items-center justify-center transition-colors ${
            isSelected
              ? "border-primary bg-primary text-primary-foreground"
              : "border-muted-foreground/40 bg-card/80 hover:border-primary/60"
          }`}
        >
          {isSelected && (
            <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
              <path d="M2.5 6L5 8.5L9.5 3.5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          )}
        </button>
      </div>
      {children}
    </div>
  );
}
