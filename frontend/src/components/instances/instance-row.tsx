import { motion } from "framer-motion";
import { ExternalLink, Play, Square, Trash2, Pause } from "lucide-react";
import { StatusBadge } from "./status-badge";
import { OverlaySparkline } from "./sparkline";
import { formatDuration } from "@/lib/utils";
import {
  useStartInstance,
  useStopInstance,
  usePauseInstance,
  useUnpauseInstance,
  useDeleteInstance,
  useInstanceStats,
} from "@/hooks/use-instances";
import { toast } from "sonner";
import type { Instance } from "@/lib/types";

interface InstanceRowProps {
  instance: Instance;
  icon: string | null;
  onSelect: (instance: Instance) => void;
}

const TRANSITION_STATES = new Set(["pulling", "starting", "stopping", "creating"]);

export function InstanceRow({ instance, icon, onSelect }: InstanceRowProps) {
  const start = useStartInstance();
  const stop = useStopInstance();
  const pause = usePauseInstance();
  const unpause = useUnpauseInstance();
  const destroy = useDeleteInstance();

  const isRunning = instance.status === "running" || instance.status === "idle";
  const isPaused = instance.status === "paused";
  const isTransitioning = TRANSITION_STATES.has(instance.status);
  const isStopped = instance.status === "stopped" || instance.status === "error";

  const { data: stats } = useInstanceStats(instance.id, isRunning);

  const uptimeSeconds = instance.started_at && isRunning
    ? (Date.now() - new Date(instance.started_at + "Z").getTime()) / 1000
    : null;

  function stop_(e: React.MouseEvent) { e.stopPropagation(); stop.mutate(instance.id, { onError: (err) => toast.error(err.message) }); }
  function start_(e: React.MouseEvent) { e.stopPropagation(); start.mutate(instance.id, { onError: (err) => toast.error(err.message) }); }
  function pause_(e: React.MouseEvent) { e.stopPropagation(); pause.mutate(instance.id, { onError: (err) => toast.error(err.message) }); }
  function unpause_(e: React.MouseEvent) { e.stopPropagation(); unpause.mutate(instance.id, { onError: (err) => toast.error(err.message) }); }
  function destroy_(e: React.MouseEvent) {
    e.stopPropagation();
    if (!confirm(`Destroy "${instance.name}"?`)) return;
    destroy.mutate({ id: instance.id, removeVolumes: false }, { onError: (err) => toast.error(err.message) });
  }

  return (
    <motion.div
      layout
      initial={{ opacity: 0, x: -10 }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0, x: 10 }}
      className="group flex items-center gap-3 rounded-lg border border-border bg-card px-3 py-2 cursor-pointer hover:border-primary/40 transition-colors"
      onClick={() => onSelect(instance)}
    >
      {/* Icon */}
      <div className={`h-8 w-8 shrink-0 flex items-center justify-center rounded-md bg-secondary overflow-hidden ${isStopped ? "grayscale opacity-30" : isPaused ? "opacity-50" : ""}`}>
        {icon?.startsWith("http") ? (
          <img src={icon} alt="" className="h-6 w-6 object-contain" />
        ) : (
          <span className="text-lg">{icon ?? "🖥️"}</span>
        )}
      </div>

      {/* Name */}
      <span className="font-medium text-sm truncate w-36 shrink-0">{instance.name}</span>

      {/* Status */}
      <div className="w-20 shrink-0">
        <StatusBadge status={instance.status} />
      </div>

      {/* Subdomain */}
      <span className="text-[10px] font-mono text-muted-foreground truncate w-28 shrink-0 hidden md:block">{instance.subdomain}</span>

      {/* Uptime */}
      <span className="text-[10px] text-muted-foreground w-16 shrink-0 hidden lg:block">
        {uptimeSeconds != null ? `↑${formatDuration(uptimeSeconds)}` : "—"}
      </span>

      {/* Sparkline */}
      <div className="flex-1 h-[20px] min-w-[60px] hidden md:block">
        {isRunning && stats ? (
          <OverlaySparkline
            series={[
              { value: stats.cpu_percent, color: "#3b82f6", label: "CPU" },
              { value: stats.memory_percent, color: "#a855f7", label: "RAM" },
            ]}
            height={20}
            points={20}
          />
        ) : (
          <div className="h-full" />
        )}
      </div>

      {/* Actions */}
      <div className="flex gap-1 shrink-0 opacity-0 group-hover:opacity-100 transition-opacity">
        {isRunning && (
          <>
            <button onClick={(e) => { e.stopPropagation(); window.open(`/i/${instance.subdomain}/`, "_blank"); }} title="Connect" className="rounded p-1 text-green-400 hover:bg-green-500/15 transition-colors">
              <ExternalLink className="h-3.5 w-3.5" />
            </button>
            <button onClick={pause_} title="Pause" className="rounded p-1 text-amber-400 hover:bg-amber-500/15 transition-colors">
              <Pause className="h-3.5 w-3.5" />
            </button>
            <button onClick={stop_} title="Stop" className="rounded p-1 text-red-400 hover:bg-red-500/15 transition-colors">
              <Square className="h-3.5 w-3.5" />
            </button>
          </>
        )}
        {isPaused && (
          <>
            <button onClick={unpause_} title="Resume" className="rounded p-1 text-green-400 hover:bg-green-500/15 transition-colors">
              <Play className="h-3.5 w-3.5" />
            </button>
            <button onClick={stop_} title="Stop" className="rounded p-1 text-red-400 hover:bg-red-500/15 transition-colors">
              <Square className="h-3.5 w-3.5" />
            </button>
          </>
        )}
        {isStopped && (
          <button onClick={start_} title="Start" className="rounded p-1 text-green-400 hover:bg-green-500/15 transition-colors">
            <Play className="h-3.5 w-3.5" />
          </button>
        )}
        {isTransitioning && (
          <span className="text-[10px] text-muted-foreground animate-pulse px-1">
            {instance.status === "pulling" ? "pulling…" : "starting…"}
          </span>
        )}
        <button onClick={destroy_} title="Destroy" className="rounded p-1 text-red-400/50 hover:text-red-400 hover:bg-red-500/15 transition-colors">
          <Trash2 className="h-3.5 w-3.5" />
        </button>
      </div>
    </motion.div>
  );
}
