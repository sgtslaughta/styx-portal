import { motion, AnimatePresence } from "framer-motion";
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

interface Props {
  instance: Instance;
  icon: string | null;
  onSelect: (instance: Instance) => void;
}

const TRANSITION_STATES = new Set(["pulling", "starting", "stopping", "creating"]);

export function InstanceCardSm({ instance, icon, onSelect }: Props) {
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
      initial={{ opacity: 0, y: 15, scale: 0.97 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      exit={{ opacity: 0, scale: 0.95 }}
      whileHover={{ y: -1 }}
      transition={{ type: "spring", stiffness: 400, damping: 30 }}
      className="group cursor-pointer overflow-hidden rounded-xl border border-border bg-card hover:border-primary/40 transition-colors"
      onClick={() => onSelect(instance)}
    >
      {/* Header — icon + name + status */}
      <div className="flex items-center gap-3 px-3 pt-3 pb-2">
        <div className={`h-10 w-10 shrink-0 flex items-center justify-center rounded-lg bg-secondary overflow-hidden ${isStopped ? "grayscale opacity-25" : isPaused ? "opacity-40" : ""}`}>
          {icon?.startsWith("http") ? (
            <img src={icon} alt="" className="h-8 w-8 object-contain" />
          ) : (
            <span className="text-xl">{icon ?? "🖥️"}</span>
          )}
        </div>
        <div className="flex-1 min-w-0">
          <h3 className="font-semibold text-sm truncate">{instance.name}</h3>
          <div className="flex items-center gap-2 mt-0.5">
            <StatusBadge status={instance.status} />
            {uptimeSeconds != null && (
              <span className="text-[10px] text-muted-foreground">↑{formatDuration(uptimeSeconds)}</span>
            )}
          </div>
        </div>
        {/* Status dot */}
        <motion.div
          className={`h-2.5 w-2.5 rounded-full shrink-0 ${
            isRunning ? "bg-green-500" : isPaused ? "bg-amber-500" : isTransitioning ? "bg-primary" : isStopped ? "bg-muted-foreground" : "bg-destructive"
          }`}
          animate={isRunning ? { scale: [1, 1.4, 1] } : isTransitioning ? { opacity: [1, 0.3, 1] } : {}}
          transition={{ duration: isRunning ? 2 : 0.6, repeat: Infinity }}
        />
      </div>

      {/* Sparkline */}
      <AnimatePresence>
        {isRunning && stats && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            className="overflow-hidden px-3"
          >
            <OverlaySparkline
              series={[
                { value: stats.cpu_percent, color: "#3b82f6", label: "CPU" },
                { value: stats.memory_percent, color: "#a855f7", label: "RAM" },
              ]}
              height={28}
            />
          </motion.div>
        )}
      </AnimatePresence>

      {/* Actions */}
      <div className="px-3 pb-3 pt-2">
        {isRunning ? (
          <div className="flex gap-1.5">
            <button onClick={(e) => { e.stopPropagation(); window.open(`/i/${instance.subdomain}/`, "_blank"); }} className="inline-flex items-center justify-center gap-1 rounded-md h-7 flex-1 text-xs bg-primary/10 text-primary hover:bg-primary/20 transition-colors">
              <ExternalLink className="h-3 w-3" /> Connect
            </button>
            <button onClick={pause_} title="Pause" className="rounded-md h-7 px-2 text-amber-400 bg-amber-500/10 hover:bg-amber-500/20 transition-colors">
              <Pause className="h-3 w-3" />
            </button>
            <button onClick={stop_} title="Stop" className="rounded-md h-7 px-2 text-red-400 bg-red-500/10 hover:bg-red-500/20 transition-colors">
              <Square className="h-3 w-3" />
            </button>
          </div>
        ) : isPaused ? (
          <div className="flex gap-1.5">
            <button onClick={unpause_} className="inline-flex items-center justify-center gap-1 rounded-md h-7 flex-1 text-xs text-green-400 bg-green-500/10 hover:bg-green-500/20 transition-colors">
              <Play className="h-3 w-3" /> Resume
            </button>
            <button onClick={stop_} title="Stop" className="rounded-md h-7 px-2 text-red-400 bg-red-500/10 hover:bg-red-500/20 transition-colors">
              <Square className="h-3 w-3" />
            </button>
          </div>
        ) : isTransitioning ? (
          <div className="h-7 flex items-center justify-center text-xs text-muted-foreground animate-pulse">
            {instance.status === "pulling" ? "Pulling…" : "Starting…"}
          </div>
        ) : (
          <div className="flex gap-1.5">
            <button onClick={start_} className="inline-flex items-center justify-center gap-1 rounded-md h-7 flex-1 text-xs text-green-400 bg-green-500/10 hover:bg-green-500/20 transition-colors">
              <Play className="h-3 w-3" /> Start
            </button>
            <button onClick={destroy_} title="Destroy" className="rounded-md h-7 px-2 text-red-400/50 hover:text-red-400 bg-red-500/5 hover:bg-red-500/15 transition-colors">
              <Trash2 className="h-3 w-3" />
            </button>
          </div>
        )}
      </div>
    </motion.div>
  );
}
