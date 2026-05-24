import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { StatusBadge } from "./status-badge";
import { api } from "@/api/client";
import { formatDuration } from "@/lib/utils";
import { useStartInstance, useStopInstance, useDeleteInstance } from "@/hooks/use-instances";
import { toast } from "sonner";
import { ExternalLink, Play, Square, Trash2 } from "lucide-react";
import type { Instance } from "@/lib/types";
import { useState } from "react";

interface InstanceDetailProps {
  instance: Instance | null;
  onClose: () => void;
}

export function InstanceDetail({ instance, onClose }: InstanceDetailProps) {
  const start = useStartInstance();
  const stop = useStopInstance();
  const destroy = useDeleteInstance();
  const [imgError, setImgError] = useState(false);

  if (!instance) return null;

  const isRunning = instance.status === "running" || instance.status === "idle";
  const idleSeconds = instance.last_activity ? (Date.now() - new Date(instance.last_activity).getTime()) / 1000 : null;
  const uptimeSeconds = instance.started_at ? (Date.now() - new Date(instance.started_at).getTime()) / 1000 : null;
  const domain = window.location.hostname === "localhost" ? "localhost" : window.location.hostname.split(".").slice(1).join(".");

  function handleDestroy() {
    if (!confirm(`Destroy "${instance!.name}"?`)) return;
    destroy.mutate({ id: instance!.id, removeVolumes: false }, {
      onSuccess: () => { toast.success("Instance destroyed"); onClose(); },
      onError: (e) => toast.error(`Destroy failed: ${e.message}`),
    });
  }

  return (
    <Dialog open={!!instance} onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="max-w-lg">
        <DialogHeader><DialogTitle>{instance.name}</DialogTitle></DialogHeader>
        <div className="aspect-video w-full overflow-hidden rounded-lg bg-secondary">
          {isRunning && !imgError ? (
            <img src={`${api.screenshotUrl(instance.id)}?t=${Math.floor(Date.now() / 30000)}`} alt={instance.name} className="h-full w-full object-cover" onError={() => setImgError(true)} />
          ) : (
            <div className="flex h-full items-center justify-center text-5xl text-muted-foreground/30">{instance.status === "stopped" ? "⏸" : "🖥️"}</div>
          )}
        </div>
        <div className="grid grid-cols-2 gap-3 text-sm">
          <div><span className="text-muted-foreground">Status</span><div className="mt-1"><StatusBadge status={instance.status} /></div></div>
          <div><span className="text-muted-foreground">Subdomain</span><div className="mt-1 font-mono text-xs">{instance.subdomain}.{domain}</div></div>
          {isRunning && <>
            <div><span className="text-muted-foreground">Uptime</span><div className="mt-1">{formatDuration(uptimeSeconds)}</div></div>
            <div><span className="text-muted-foreground">Idle</span><div className="mt-1">{formatDuration(idleSeconds)}</div></div>
          </>}
        </div>
        {instance.session_config && <>
          <Separator />
          <div className="grid grid-cols-2 gap-2 text-xs">
            <div><span className="text-muted-foreground">Idle Timeout:</span> {instance.session_config.idle_timeout}</div>
            <div><span className="text-muted-foreground">Grace Period:</span> {instance.session_config.grace_period}</div>
            <div><span className="text-muted-foreground">Action:</span> {instance.session_config.timeout_action}</div>
            <div><span className="text-muted-foreground">Never Timeout:</span> {instance.session_config.never_timeout ? "Yes" : "No"}</div>
          </div>
        </>}
        <Separator />
        <div className="flex gap-2">
          {isRunning ? <>
            <Button className="flex-1" onClick={() => window.open(`/i/${instance.subdomain}/`, "_blank")}><ExternalLink className="mr-2 h-3 w-3" /> Connect</Button>
            <Button variant="secondary" onClick={() => stop.mutate(instance.id, { onError: (e) => toast.error(e.message) })}><Square className="mr-2 h-3 w-3" /> Stop</Button>
          </> : (
            <Button className="flex-1" onClick={() => start.mutate(instance.id, { onError: (e) => toast.error(e.message) })}><Play className="mr-2 h-3 w-3" /> Start</Button>
          )}
          <Button variant="destructive" onClick={handleDestroy}><Trash2 className="mr-2 h-3 w-3" /> Destroy</Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
