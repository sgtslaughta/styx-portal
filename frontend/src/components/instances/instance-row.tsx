import { motion } from "framer-motion";
import { StatusBadge } from "./status-badge";
import { OverlaySparkline } from "./sparkline";
import { ActionBar } from "@/components/common/action-bar";
import { formatDuration } from "@/lib/utils";
import { useInstanceStats } from "@/hooks/use-instances";
import { useFadeSlideIn, spring } from "@/lib/motion";
import { CHART_COLORS } from "@/lib/chart";
import type { Instance } from "@/lib/types";

interface InstanceRowProps {
  instance: Instance;
  icon: string | null;
  onSelect: (instance: Instance) => void;
}

export function InstanceRow({ instance, icon, onSelect }: InstanceRowProps) {
  const isRunning = instance.status === "running" || instance.status === "idle";
  const isPaused = instance.status === "paused";
  const isStopped = instance.status === "stopped" || instance.status === "error";

  const { data: stats } = useInstanceStats(instance.id, isRunning);
  const variants = useFadeSlideIn();

  const uptimeSeconds = instance.started_at && isRunning
    ? (Date.now() - new Date(instance.started_at + "Z").getTime()) / 1000
    : null;

  return (
    <motion.div
      layout
      variants={variants}
      initial="initial"
      animate="animate"
      exit="exit"
      transition={spring}
      className="styx-card group flex items-center gap-3 rounded-lg px-3 py-2 cursor-pointer hover:border-primary/40 transition-colors"
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
      <span className="font-medium text-sm truncate w-36 shrink-0" title={instance.name}>{instance.name}</span>

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
              { value: stats.cpu_percent, color: CHART_COLORS.cpu, label: "CPU" },
              { value: stats.memory_percent, color: CHART_COLORS.memory, label: "RAM" },
            ]}
            height={20}
            points={20}
          />
        ) : (
          <div className="h-full" />
        )}
      </div>

      {/* Actions */}
      <div className="opacity-0 group-hover:opacity-100 transition-opacity">
        <ActionBar instance={instance} size="sm" className="gap-1" />
      </div>
    </motion.div>
  );
}
