import { useState } from "react";
import { motion, AnimatePresence, useReducedMotion } from "framer-motion";
import { cn } from "@/lib/utils";
import {
  useInstances,
  useStartInstance,
  useStopInstance,
  useRestartInstance,
  usePauseInstance,
  useUnpauseInstance,
  useDeleteInstance,
} from "@/hooks/use-instances";
import { useSessionEvents } from "@/hooks/use-system";
import { StatusBadge } from "@/components/instances/status-badge";
import { ConfirmDialog } from "@/components/common/confirm-dialog";
import { formatDuration } from "@/lib/utils";
import {
  Play,
  Square,
  RotateCcw,
  Pause,
  Trash2,
  ChevronDown,
  Filter,
  ExternalLink,
  type LucideIcon,
} from "lucide-react";
import { toast } from "sonner";
import type { Instance } from "@/lib/types";

const STATUS_FILTERS = ["all", "running", "stopped", "error", "paused"] as const;

export function MetricsSessions() {
  const { data: instances } = useInstances();
  const [filter, setFilter] = useState<string>("all");
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [destroyTarget, setDestroyTarget] = useState<Instance | null>(null);

  const filtered = instances?.filter((inst) => {
    if (filter === "all") return true;
    if (filter === "running") return inst.status === "running" || inst.status === "idle";
    return inst.status === filter;
  }) ?? [];

  return (
    <div className="space-y-4">
      {/* Filters */}
      <div className="flex items-center gap-2">
        <Filter className="h-3.5 w-3.5 text-muted-foreground" />
        {STATUS_FILTERS.map((f) => (
          <button
            key={f}
            onClick={() => setFilter(f)}
            className={cn(
              "rounded-md px-2.5 py-1 text-[11px] font-medium transition-colors",
              filter === f
                ? "bg-secondary text-foreground"
                : "text-muted-foreground hover:text-foreground/80 hover:bg-muted/50"
            )}
          >
            {f.charAt(0).toUpperCase() + f.slice(1)}
            {f !== "all" && instances && (
              <span className="ml-1 text-muted-foreground/60">
                {instances.filter((i) =>
                  f === "running" ? i.status === "running" || i.status === "idle" : i.status === f
                ).length}
              </span>
            )}
          </button>
        ))}
      </div>

      {/* Session Table */}
      <div className="styx-card rounded-lg overflow-hidden">
        {/* Header */}
        <div className="grid grid-cols-[1fr_100px_80px_80px_140px] gap-2 px-4 py-2.5 border-b border-border/40 text-[10px] uppercase tracking-wider text-muted-foreground/60 font-medium">
          <span>Instance</span>
          <span>Status</span>
          <span>Uptime</span>
          <span>Idle</span>
          <span className="text-right">Actions</span>
        </div>

        {/* Rows */}
        <div className="divide-y divide-border/40">
          {filtered.length === 0 ? (
            <div className="py-8 text-center text-xs text-muted-foreground/60">
              No instances match filter
            </div>
          ) : (
            filtered.map((inst) => (
              <SessionRow
                key={inst.id}
                instance={inst}
                expanded={expandedId === inst.id}
                onToggle={() => setExpandedId(expandedId === inst.id ? null : inst.id)}
                onDestroyClick={(inst) => setDestroyTarget(inst)}
              />
            ))
          )}
        </div>
      </div>

      {/* Destroy confirmation dialog */}
      {destroyTarget && (
        <DestroyDialog
          instance={destroyTarget}
          onOpenChange={(open) => !open && setDestroyTarget(null)}
          onConfirm={() => setDestroyTarget(null)}
        />
      )}
    </div>
  );
}

function DestroyDialog({
  instance,
  onOpenChange,
  onConfirm,
}: {
  instance: Instance;
  onOpenChange: (open: boolean) => void;
  onConfirm: () => void;
}) {
  const destroy = useDeleteInstance();

  function handleDestroy() {
    destroy.mutate({ id: instance.id, removeVolumes: false }, {
      onSuccess: () => {
        toast.success(`Destroyed "${instance.name}"`);
        onConfirm();
      },
      onError: (e) => toast.error(e.message),
    });
  }

  return (
    <ConfirmDialog
      open={true}
      onOpenChange={onOpenChange}
      title="Destroy Instance"
      description={`This action cannot be undone. All data in this instance will be lost.`}
      confirmPhrase={instance.name}
      variant="destructive"
      confirmLabel="Destroy"
      onConfirm={handleDestroy}
    />
  );
}

function SessionRow({
  instance,
  expanded,
  onToggle,
  onDestroyClick,
}: {
  instance: Instance;
  expanded: boolean;
  onToggle: () => void;
  onDestroyClick: (inst: Instance) => void;
}) {
  const start = useStartInstance();
  const stop = useStopInstance();
  const restart = useRestartInstance();
  const pause = usePauseInstance();
  const unpause = useUnpauseInstance();
  const reduce = useReducedMotion();
  const { data: events } = useSessionEvents(instance.id, expanded);

  const isRunning = instance.status === "running" || instance.status === "idle";
  const isPaused = instance.status === "paused";

  const uptimeSeconds = instance.started_at && isRunning
    ? (Date.now() - new Date(instance.started_at + "Z").getTime()) / 1000
    : null;
  const idleSeconds = instance.last_activity && isRunning
    ? (Date.now() - new Date(instance.last_activity + "Z").getTime()) / 1000
    : null;

  return (
    <div>
      <div
        className="grid grid-cols-[1fr_100px_80px_80px_140px] gap-2 px-4 py-2.5 items-center hover:bg-muted/20 transition-colors cursor-pointer"
        onClick={onToggle}
      >
        <div className="flex items-center gap-2.5 min-w-0">
          <ChevronDown
            className={cn(
              "h-3 w-3 text-muted-foreground/60 transition-transform shrink-0",
              expanded && "rotate-180"
            )}
          />
          <span className="text-sm text-foreground truncate">{instance.name}</span>
          <span className="text-[10px] text-muted-foreground/60 font-mono truncate">{instance.subdomain}</span>
        </div>
        <StatusBadge status={instance.status} />
        <span className="text-xs text-muted-foreground tabular-nums">
          {uptimeSeconds != null ? formatDuration(uptimeSeconds) : "—"}
        </span>
        <span className={cn("text-xs tabular-nums", idleSeconds && idleSeconds > 300 ? "text-warning" : "text-muted-foreground")}>
          {idleSeconds != null ? formatDuration(idleSeconds) : "—"}
        </span>
        <div className="flex gap-1 justify-end" onClick={(e) => e.stopPropagation()}>
          {isRunning && (
            <>
              <ActionBtn icon={ExternalLink} color="emerald" title="Connect" onClick={() => window.open(`/i/${instance.subdomain}/`, "_blank")} />
              <ActionBtn icon={RotateCcw} color="blue" title="Restart" onClick={() => restart.mutate(instance.id, { onError: (e) => toast.error(e.message) })} />
              <ActionBtn icon={Pause} color="warning" title="Pause" onClick={() => pause.mutate(instance.id, { onError: (e) => toast.error(e.message) })} />
              <ActionBtn icon={Square} color="destructive" title="Stop" onClick={() => stop.mutate(instance.id, { onError: (e) => toast.error(e.message) })} />
            </>
          )}
          {isPaused && (
            <>
              <ActionBtn icon={Play} color="emerald" title="Resume" onClick={() => unpause.mutate(instance.id, { onError: (e) => toast.error(e.message) })} />
              <ActionBtn icon={Square} color="destructive" title="Stop" onClick={() => stop.mutate(instance.id, { onError: (e) => toast.error(e.message) })} />
            </>
          )}
          {!isRunning && !isPaused && (
            <>
              <ActionBtn icon={Play} color="emerald" title="Start" onClick={() => start.mutate(instance.id, { onError: (e) => toast.error(e.message) })} />
              <ActionBtn icon={Trash2} color="destructive" title="Destroy" onClick={() => onDestroyClick(instance)} />
            </>
          )}
        </div>
      </div>

      {/* Expanded event timeline */}
      <AnimatePresence>
        {expanded && (
          <motion.div
            initial={reduce ? undefined : { height: 0, opacity: 0 }}
            animate={reduce ? undefined : { height: "auto", opacity: 1 }}
            exit={reduce ? undefined : { height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="overflow-hidden"
          >
            <div className="px-4 pb-3 pt-1 ml-7">
              {instance.error_message && (
                <div className="mb-2 rounded-md bg-destructive/10 border border-destructive/20 px-3 py-2 text-[11px] text-destructive/80">
                  {instance.error_message}
                </div>
              )}
              <div className="border-l-2 border-border pl-3 space-y-1.5">
                {(!events || events.length === 0) ? (
                  <span className="text-[11px] text-muted-foreground/60">No events recorded</span>
                ) : (
                  events.slice(0, 10).map((ev, i) => (
                    <div key={i} className="flex items-center gap-2 text-[11px]">
                      <span className="text-muted-foreground/60 tabular-nums w-20">{ev.time}</span>
                      <span className={cn(
                        "font-medium",
                        ev.type === "error" ? "text-destructive" :
                        ev.type === "started" ? "text-emerald-400" :
                        ev.type === "stopped" ? "text-muted-foreground" :
                        "text-blue-400"
                      )}>
                        {ev.type}
                      </span>
                      {ev.details && <span className="text-muted-foreground/60 truncate">{ev.details}</span>}
                    </div>
                  ))
                )}
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function ActionBtn({
  icon: Icon,
  color,
  title,
  onClick,
}: {
  icon: LucideIcon;
  color: "emerald" | "blue" | "warning" | "destructive";
  title: string;
  onClick: () => void;
}) {
  const colors = {
    emerald: "text-emerald-400 hover:bg-emerald-500/15",
    blue: "text-blue-400 hover:bg-blue-500/15",
    warning: "text-warning hover:bg-warning/15",
    destructive: "text-destructive hover:bg-destructive/15",
  };
  return (
    <button
      onClick={onClick}
      title={title}
      className={cn("rounded p-1 transition-colors", colors[color])}
    >
      <Icon className="h-3.5 w-3.5" />
    </button>
  );
}
