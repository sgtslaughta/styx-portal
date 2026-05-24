import { MoreHorizontal, ExternalLink, Play, Square, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { StatusBadge } from "./status-badge";
import { api } from "@/api/client";
import { formatDuration } from "@/lib/utils";
import { useStartInstance, useStopInstance, useDeleteInstance } from "@/hooks/use-instances";
import { toast } from "sonner";
import type { Instance } from "@/lib/types";
import { useState } from "react";

interface InstanceCardProps {
  instance: Instance;
  domain: string;
  onSelect: (instance: Instance) => void;
}

export function InstanceCard({ instance, domain, onSelect }: InstanceCardProps) {
  const start = useStartInstance();
  const stop = useStopInstance();
  const destroy = useDeleteInstance();
  const [imgError, setImgError] = useState(false);

  const isRunning = instance.status === "running" || instance.status === "idle";
  const idleSeconds = instance.last_activity
    ? (Date.now() - new Date(instance.last_activity).getTime()) / 1000
    : null;

  function handleConnect() {
    window.open(`https://${instance.subdomain}.${domain}`, "_blank");
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
      <div className="relative aspect-video w-full bg-secondary">
        {isRunning && !imgError ? (
          <img
            src={`${api.screenshotUrl(instance.id)}?t=${Math.floor(Date.now() / 30000)}`}
            alt={instance.name}
            className="h-full w-full object-cover"
            onError={() => setImgError(true)}
          />
        ) : (
          <div className="flex h-full items-center justify-center text-4xl text-muted-foreground/30">
            {instance.status === "stopped" ? "⏸" : "🖥️"}
          </div>
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
            <DropdownMenuContent align="end">
              {isRunning && (
                <DropdownMenuItem onClick={handleStop}>
                  <Square className="mr-2 h-3 w-3" /> Stop
                </DropdownMenuItem>
              )}
              {!isRunning && (
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

        <div className="mb-3 flex items-center gap-3">
          <StatusBadge status={instance.status} />
          {isRunning && idleSeconds != null && (
            <span className="text-xs text-muted-foreground">
              {formatDuration(idleSeconds)} idle
            </span>
          )}
        </div>

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
