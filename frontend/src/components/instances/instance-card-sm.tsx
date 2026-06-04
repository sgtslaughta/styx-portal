import { motion, AnimatePresence } from "framer-motion";
import { StatusBadge } from "./status-badge";
import { OverlaySparkline } from "./sparkline";
import { ActionBar } from "@/components/common/action-bar";
import { formatDuration } from "@/lib/utils";
import { useInstanceStats } from "@/hooks/use-instances";
import { statusMeta } from "@/lib/status";
import { fadeSlideIn, hoverLift, spring } from "@/lib/motion";
import { CHART_COLORS } from "@/lib/chart";
import type { Instance } from "@/lib/types";

interface Props {
  instance: Instance;
  icon: string | null;
  onSelect: (instance: Instance) => void;
}

export function InstanceCardSm({ instance, icon, onSelect }: Props) {
  const isRunning = instance.status === "running" || instance.status === "idle";
  const isPaused = instance.status === "paused";
  const isStopped = instance.status === "stopped" || instance.status === "error";

  const { data: stats } = useInstanceStats(instance.id, isRunning);
  const { dotClass, pulse } = statusMeta(instance.status);

  const uptimeSeconds = instance.started_at && isRunning
    ? (Date.now() - new Date(instance.started_at + "Z").getTime()) / 1000
    : null;

  return (
    <motion.div
      layout
      variants={fadeSlideIn}
      initial="initial"
      animate="animate"
      exit="exit"
      whileHover={hoverLift}
      transition={spring}
      className="styx-card group cursor-pointer overflow-hidden rounded-xl hover:border-primary/40 transition-colors"
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
        <div
          className={`h-2.5 w-2.5 rounded-full shrink-0 ${dotClass} ${pulse ? "animate-pulse" : ""}`}
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
                { value: stats.cpu_percent, color: CHART_COLORS.cpu, label: "CPU" },
                { value: stats.memory_percent, color: CHART_COLORS.memory, label: "RAM" },
              ]}
              height={28}
            />
          </motion.div>
        )}
      </AnimatePresence>

      {/* Actions */}
      <div className="px-3 pb-3 pt-2">
        <ActionBar instance={instance} size="sm" />
      </div>
    </motion.div>
  );
}
