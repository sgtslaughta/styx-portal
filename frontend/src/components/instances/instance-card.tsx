import { motion, AnimatePresence } from "framer-motion";
import { StatusBadge } from "./status-badge";
import { OverlaySparkline } from "./sparkline";
import { IconViewport } from "./icon-viewport";
import { ActionBar } from "@/components/common/action-bar";
import { formatDuration } from "@/lib/utils";
import { useInstanceStats } from "@/hooks/use-instances";
import { fadeSlideIn, hoverLift, spring, listStagger } from "@/lib/motion";
import { CHART_COLORS } from "@/lib/chart";
import type { Instance } from "@/lib/types";

interface InstanceCardProps {
  instance: Instance;
  icon: string | null;
  onSelect: (instance: Instance) => void;
}

export function InstanceCard({ instance, icon, onSelect }: InstanceCardProps) {
  const isRunning = instance.status === "running" || instance.status === "idle";

  const { data: stats } = useInstanceStats(instance.id, isRunning);

  const uptimeSeconds = instance.started_at && isRunning
    ? (Date.now() - new Date(instance.started_at + "Z").getTime()) / 1000
    : null;
  const idleSeconds = instance.last_activity && isRunning
    ? (Date.now() - new Date(instance.last_activity + "Z").getTime()) / 1000
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
      className="group cursor-pointer overflow-hidden rounded-xl border border-border bg-card transition-colors hover:border-primary/50"
      onClick={() => onSelect(instance)}
    >
      <IconViewport instance={instance} icon={icon} />

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
                className="text-[10px] text-warning"
              >
                idle {formatDuration(idleSeconds)}
              </motion.span>
            )}
          </AnimatePresence>
        </div>

        {/* Error message */}
        {instance.status === "error" && instance.error_message && (
          <div className="rounded-md bg-destructive/10 border border-destructive/20 px-2.5 py-1.5 text-[11px] text-destructive leading-tight break-all">
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
                  { value: stats.cpu_percent, color: CHART_COLORS.cpu, label: "CPU" },
                  { value: stats.memory_percent, color: CHART_COLORS.memory, label: "RAM" },
                ]}
                height={36}
              />
            </motion.div>
          )}
        </AnimatePresence>

        {/* Actions */}
        <ActionBar instance={instance} size="sm" />
      </div>
    </motion.div>
  );
}
