import { motion, AnimatePresence } from "framer-motion";
import { MoreHorizontal, ExternalLink, Play, Square, Trash2, Pause, RotateCcw } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { StatusBadge } from "./status-badge";
import { OverlaySparkline } from "./sparkline";
import { formatDuration } from "@/lib/utils";
import {
  useStartInstance,
  useStopInstance,
  useRestartInstance,
  usePauseInstance,
  useUnpauseInstance,
  useDeleteInstance,
  useInstanceStats,
} from "@/hooks/use-instances";
import { toast } from "sonner";
import type { Instance } from "@/lib/types";

interface InstanceCardProps {
  instance: Instance;
  icon: string | null;
  onSelect: (instance: Instance) => void;
}

const TRANSITION_STATES = new Set(["pulling", "starting", "stopping", "creating"]);

export function InstanceCard({ instance, icon, onSelect }: InstanceCardProps) {
  const start = useStartInstance();
  const stop = useStopInstance();
  const restart = useRestartInstance();
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
  const idleSeconds = instance.last_activity && isRunning
    ? (Date.now() - new Date(instance.last_activity + "Z").getTime()) / 1000
    : null;

  function handleConnect(e: React.MouseEvent) {
    e.stopPropagation();
    window.open(`/i/${instance.subdomain}/`, "_blank");
  }

  function handleStart(e: React.MouseEvent) {
    e.stopPropagation();
    start.mutate(instance.id, { onError: (err) => toast.error(`Start failed: ${err.message}`) });
  }

  function handleStop(e: React.MouseEvent) {
    e.stopPropagation();
    stop.mutate(instance.id, { onError: (err) => toast.error(`Stop failed: ${err.message}`) });
  }

  function handleRestart(e: React.MouseEvent) {
    e.stopPropagation();
    restart.mutate(instance.id, { onError: (err) => toast.error(`Restart failed: ${err.message}`) });
  }

  function handlePause(e: React.MouseEvent) {
    e.stopPropagation();
    pause.mutate(instance.id, { onError: (err) => toast.error(`Pause failed: ${err.message}`) });
  }

  function handleUnpause(e: React.MouseEvent) {
    e.stopPropagation();
    unpause.mutate(instance.id, { onError: (err) => toast.error(`Resume failed: ${err.message}`) });
  }

  function handleDestroy(e: React.MouseEvent) {
    e.stopPropagation();
    if (!confirm(`Destroy "${instance.name}"? This removes the container.`)) return;
    destroy.mutate(
      { id: instance.id, removeVolumes: false },
      { onError: (err) => toast.error(`Destroy failed: ${err.message}`) }
    );
  }

  const iconContent = instance.status === "pulling" ? (
    <span className="text-[16rem] leading-none select-none">⏳</span>
  ) : icon?.startsWith("http") ? (
    <img src={icon} alt={instance.name} className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[130%] h-[130%] object-contain" draggable={false} />
  ) : (
    <span className="text-[16rem] leading-none select-none">{icon ?? "🖥️"}</span>
  );

  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 20, scale: 0.95 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      exit={{ opacity: 0, scale: 0.9, y: -10 }}
      whileHover={{ y: -2 }}
      transition={{ type: "spring", stiffness: 400, damping: 30 }}
      className="group cursor-pointer overflow-hidden rounded-xl border border-border bg-card transition-colors hover:border-primary/50"
      onClick={() => onSelect(instance)}
    >
      {/* Icon viewport — 2x icon, overflow crops */}
      <div className="relative aspect-video w-full bg-secondary overflow-hidden flex items-center justify-center">
        {/* Single persistent icon — no AnimatePresence remount */}
        <motion.div
          className={`relative flex items-center justify-center w-full h-full ${isStopped ? "grayscale opacity-20" : isPaused ? "opacity-40 saturate-50" : ""}`}
          animate={
            isRunning
              ? {
                  scale: [1, 1.06, 1],
                  y: [0, -5, 0],
                  rotate: [0, 1, -1, 0],
                }
              : isTransitioning
                ? {
                    scale: [0.95, 1.08, 0.95],
                    rotate: [0, 4, -4, 0],
                  }
                : { scale: 1 }
          }
          transition={
            isRunning
              ? { duration: 4, repeat: Infinity, ease: "easeInOut", repeatType: "loop" as const }
              : isTransitioning
                ? { duration: 1.2, repeat: Infinity, ease: "easeInOut", repeatType: "loop" as const }
                : { duration: 0.3 }
          }
          style={{
            filter: isRunning
              ? "drop-shadow(0 0 24px rgba(34,197,94,0.5))"
              : isTransitioning
                ? "drop-shadow(0 0 18px rgba(99,102,241,0.5))"
                : "none",
          }}
        >
          {iconContent}
        </motion.div>

        {/* Hero name overlay — bottom left */}
        <div className="absolute bottom-0 left-0 right-0 px-3 pb-2 pt-8" style={{ background: "linear-gradient(to top, rgba(0,0,0,0.7) 0%, transparent 100%)" }}>
          <h3 className="text-lg font-bold text-white truncate drop-shadow-lg">{instance.name}</h3>
        </div>

        {/* Status dot */}
        <motion.div
          className={`absolute top-2.5 right-2.5 h-3 w-3 rounded-full ${
            isRunning ? "bg-green-500" : isPaused ? "bg-amber-500" : isTransitioning ? "bg-primary" : isStopped ? "bg-muted-foreground" : "bg-destructive"
          }`}
          animate={
            isRunning
              ? { scale: [1, 1.5, 1], boxShadow: ["0 0 0px rgba(34,197,94,0.4)", "0 0 14px rgba(34,197,94,0.9)", "0 0 0px rgba(34,197,94,0.4)"] }
              : isTransitioning
                ? { opacity: [1, 0.2, 1], scale: [1, 1.4, 1] }
                : {}
          }
          transition={{ duration: isRunning ? 2 : 0.5, repeat: Infinity }}
        />

        {/* Menu — top left */}
        <div className="absolute top-2 left-2">
          <DropdownMenu>
            <DropdownMenuTrigger asChild onClick={(e) => e.stopPropagation()}>
              <Button variant="ghost" size="icon" className="h-7 w-7 text-white/70 hover:text-white hover:bg-white/10 opacity-0 group-hover:opacity-100 transition-opacity">
                <MoreHorizontal className="h-4 w-4" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" onClick={(e) => e.stopPropagation()}>
              {isRunning && (
                <>
                  <DropdownMenuItem onClick={handleRestart}>
                    <RotateCcw className="mr-2 h-3 w-3" /> Restart
                  </DropdownMenuItem>
                  <DropdownMenuItem onClick={handlePause}>
                    <Pause className="mr-2 h-3 w-3" /> Pause
                  </DropdownMenuItem>
                  <DropdownMenuItem onClick={handleStop}>
                    <Square className="mr-2 h-3 w-3" /> Stop
                  </DropdownMenuItem>
                </>
              )}
              {isPaused && (
                <>
                  <DropdownMenuItem onClick={handleUnpause}>
                    <Play className="mr-2 h-3 w-3" /> Resume
                  </DropdownMenuItem>
                  <DropdownMenuItem onClick={handleStop}>
                    <Square className="mr-2 h-3 w-3" /> Stop
                  </DropdownMenuItem>
                </>
              )}
              {isStopped && (
                <DropdownMenuItem onClick={handleStart}>
                  <Play className="mr-2 h-3 w-3" /> Start
                </DropdownMenuItem>
              )}
              <DropdownMenuItem onClick={handleDestroy} className="text-destructive">
                <Trash2 className="mr-2 h-3 w-3" /> Destroy
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </div>

      <div className="p-3 space-y-2">
        {/* Status + timing */}
        <div className="flex items-center gap-3">
          <StatusBadge status={instance.status} />
          <AnimatePresence>
            {isRunning && uptimeSeconds != null && (
              <motion.span
                initial={{ opacity: 0, x: -5 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0 }}
                className="text-[10px] text-muted-foreground"
              >
                ↑{formatDuration(uptimeSeconds)}
              </motion.span>
            )}
            {isRunning && idleSeconds != null && idleSeconds > 60 && (
              <motion.span
                initial={{ opacity: 0, x: -5 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0 }}
                className="text-[10px] text-yellow-500"
              >
                idle {formatDuration(idleSeconds)}
              </motion.span>
            )}
          </AnimatePresence>
        </div>

        {/* Error message */}
        {instance.status === "error" && instance.error_message && (
          <div className="rounded-md bg-red-500/10 border border-red-500/20 px-2.5 py-1.5 text-[11px] text-red-400 leading-tight break-all">
            {instance.error_message}
          </div>
        )}

        {/* Overlaid sparkline — CPU + RAM */}
        <AnimatePresence>
          {isRunning && stats && (
            <motion.div
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: "auto", opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              className="overflow-hidden"
            >
              <OverlaySparkline
                series={[
                  { value: stats.cpu_percent, color: "#3b82f6", label: "CPU" },
                  { value: stats.memory_percent, color: "#a855f7", label: "RAM" },
                ]}
                height={36}
              />
            </motion.div>
          )}
        </AnimatePresence>

        {/* Action button */}
        <motion.div layout>
          {isRunning ? (
            <div className="flex gap-1.5">
              <Button size="sm" className="flex-1 gap-1.5" onClick={handleConnect}>
                <ExternalLink className="h-3 w-3" /> Connect
              </Button>
              <button onClick={handlePause} title="Pause" className="inline-flex items-center justify-center rounded-md px-2.5 h-8 text-amber-400 bg-amber-500/10 hover:bg-amber-500/25 hover:text-amber-300 transition-colors">
                <Pause className="h-3.5 w-3.5" />
              </button>
              <button onClick={handleStop} title="Stop" className="inline-flex items-center justify-center rounded-md px-2.5 h-8 text-red-400 bg-red-500/10 hover:bg-red-500/25 hover:text-red-300 transition-colors">
                <Square className="h-3.5 w-3.5" />
              </button>
            </div>
          ) : isPaused ? (
            <div className="flex gap-1.5">
              <button onClick={handleUnpause} className="inline-flex items-center justify-center gap-1.5 rounded-md px-3 h-8 flex-1 text-sm text-green-400 bg-green-500/10 hover:bg-green-500/25 hover:text-green-300 transition-colors">
                <Play className="h-3.5 w-3.5" /> Resume
              </button>
              <button onClick={handleStop} title="Stop" className="inline-flex items-center justify-center rounded-md px-2.5 h-8 text-red-400 bg-red-500/10 hover:bg-red-500/25 hover:text-red-300 transition-colors">
                <Square className="h-3.5 w-3.5" />
              </button>
            </div>
          ) : isTransitioning ? (
            <Button size="sm" variant="secondary" className="w-full" disabled>
              <motion.span
                animate={{ opacity: [0.5, 1, 0.5] }}
                transition={{ duration: 1.5, repeat: Infinity }}
              >
                {instance.status === "pulling" ? "Pulling image..." : "Starting..."}
              </motion.span>
            </Button>
          ) : (
            <button onClick={handleStart} className="inline-flex items-center justify-center gap-1.5 rounded-md px-3 h-8 w-full text-sm text-green-400 bg-green-500/10 hover:bg-green-500/25 hover:text-green-300 transition-colors">
              <Play className="h-3.5 w-3.5" /> Start
            </button>
          )}
        </motion.div>
      </div>
    </motion.div>
  );
}
