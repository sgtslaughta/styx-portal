import { MoreHorizontal, ExternalLink, Play, Square, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { StatusBadge } from "./status-badge";
import { formatDuration } from "@/lib/utils";
import { useStartInstance, useStopInstance, useDeleteInstance, useInstanceStats } from "@/hooks/use-instances";
import { toast } from "sonner";
import type { Instance } from "@/lib/types";

interface InstanceCardProps {
  instance: Instance;
  icon: string | null;
  onSelect: (instance: Instance) => void;
}

export function InstanceCard({ instance, icon, onSelect }: InstanceCardProps) {
  const start = useStartInstance();
  const stop = useStopInstance();
  const destroy = useDeleteInstance();

  const isRunning = instance.status === "running" || instance.status === "idle";
  const { data: stats } = useInstanceStats(instance.id, isRunning);
  const idleSeconds = instance.last_activity
    ? (Date.now() - new Date(instance.last_activity).getTime()) / 1000
    : null;

  function handleConnect() {
    window.open(`/i/${instance.subdomain}/`, "_blank");
  }

  function handleStart() {
    start.mutate(instance.id, {
      onError: (e) => toast.error(`Start failed: ${e.message}`),
    });
  }

  function handleStop() {
    stop.mutate(instance.id, {
      onError: (e) => toast.error(`Stop failed: ${e.message}`),
    });
  }

  function handleDestroy() {
    if (!confirm(`Destroy "${instance.name}"? This removes the container.`)) return;
    destroy.mutate(
      { id: instance.id, removeVolumes: false },
      { onError: (e) => toast.error(`Destroy failed: ${e.message}`) }
    );
  }

  return (
    <div
      className="group cursor-pointer overflow-hidden rounded-xl border border-border bg-card transition-colors hover:border-primary/50"
      onClick={() => onSelect(instance)}
    >
      <div className="relative aspect-video w-full bg-secondary flex items-center justify-center">
        {instance.status === "pulling" ? (
          <div className="text-4xl">⏳</div>
        ) : icon?.startsWith("http") ? (
          <img src={icon} alt={instance.name} className="h-16 w-16 object-contain" />
        ) : (
          <div className="text-4xl">{icon ?? "🖥️"}</div>
        )}
      </div>

      <div className="p-4">
        <div className="mb-2 flex items-center gap-2">
          <h3 className="flex-1 truncate font-semibold">{instance.name}</h3>
          <DropdownMenu>
            <DropdownMenuTrigger asChild onClick={(e) => e.stopPropagation()}>
              <Button variant="ghost" size="icon" className="h-7 w-7">
                <MoreHorizontal className="h-4 w-4" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" onClick={(e) => e.stopPropagation()}>
              {isRunning && (
                <DropdownMenuItem onClick={(e) => { e.stopPropagation(); handleStop(); }}>
                  <Square className="mr-2 h-3 w-3" /> Stop
                </DropdownMenuItem>
              )}
              {!isRunning && (
                <DropdownMenuItem onClick={(e) => { e.stopPropagation(); handleStart(); }}>
                  <Play className="mr-2 h-3 w-3" /> Start
                </DropdownMenuItem>
              )}
              <DropdownMenuItem onClick={(e) => { e.stopPropagation(); handleDestroy(); }} className="text-destructive">
                <Trash2 className="mr-2 h-3 w-3" /> Destroy
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>

        <div className="mb-2 flex items-center gap-3">
          <StatusBadge status={instance.status} />
          {isRunning && idleSeconds != null && (
            <span className="text-xs text-muted-foreground">
              {formatDuration(idleSeconds)} idle
            </span>
          )}
        </div>

        {isRunning && stats && (
          <div className="mb-3 flex items-center gap-3 text-[10px] text-muted-foreground">
            <span>CPU {stats.cpu_percent}%</span>
            <span>RAM {stats.memory_mb}MB / {stats.memory_limit_mb}MB ({stats.memory_percent}%)</span>
          </div>
        )}

        {isRunning ? (
          <Button size="sm" className="w-full" onClick={(e) => { e.stopPropagation(); handleConnect(); }}>
            <ExternalLink className="mr-2 h-3 w-3" /> Connect
          </Button>
        ) : (
          <Button size="sm" variant="secondary" className="w-full" onClick={(e) => { e.stopPropagation(); handleStart(); }}>
            <Play className="mr-2 h-3 w-3" /> Start
          </Button>
        )}
      </div>
    </div>
  );
}
