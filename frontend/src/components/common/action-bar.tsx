import * as React from "react";
import { toast } from "sonner";
import { ExternalLink, Pause, Play, RotateCcw, Square, Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/common/confirm-dialog";
import { statusMeta } from "@/lib/status";
import { cn } from "@/lib/utils";
import {
  useDeleteInstance, usePauseInstance, useRestartInstance,
  useStartInstance, useStopInstance, useUnpauseInstance,
} from "@/hooks/use-instances";
import type { Instance } from "@/lib/types";

interface ActionBarProps {
  instance: Instance;
  size?: "sm" | "default";
  showConnect?: boolean;
  className?: string;
}

type SimpleMutation = { mutate: (id: string, opts?: { onError?: (e: Error) => void; onSuccess?: () => void }) => void };

export function ActionBar({ instance, size = "default", showConnect = true, className }: ActionBarProps) {
  const start = useStartInstance();
  const stop = useStopInstance();
  const restart = useRestartInstance();
  const pause = usePauseInstance();
  const unpause = useUnpauseInstance();
  const destroy = useDeleteInstance();
  const [confirmOpen, setConfirmOpen] = React.useState(false);
  const [removeImage, setRemoveImage] = React.useState(false);
  const [removeTemplate, setRemoveTemplate] = React.useState(false);

  // Reset the opt-in checkboxes whenever the dialog closes.
  React.useEffect(() => {
    if (!confirmOpen) {
      setRemoveImage(false);
      setRemoveTemplate(false);
    }
  }, [confirmOpen]);

  const { group, label } = statusMeta(instance.status);
  const btn = size === "sm" ? "sm" : "default";

  function run(mut: SimpleMutation, verb: string) {
    return () => mut.mutate(instance.id, { onError: (e: Error) => toast.error(`${verb} failed: ${e.message}`) });
  }

  function doDestroy() {
    destroy.mutate(
      { id: instance.id, removeVolumes: false, removeImage, removeTemplate },
      {
        onError: (e: Error) => toast.error(`Destroy failed: ${e.message}`),
        onSuccess: () => toast.success(`Destroyed ${instance.name}`),
      }
    );
  }

  function connect() {
    window.open(`/i/${instance.subdomain}/`, "_blank");
  }

  return (
    <div className={cn("flex items-center gap-1.5", className)}>
      {group === "running" && (
        <>
          {showConnect && (
            <Button size={btn} onClick={connect}>
              <ExternalLink /> Connect
            </Button>
          )}
          <Button size={btn} variant="secondary" title="Restart" onClick={run(restart, "Restart")} aria-label="Restart">
            <RotateCcw />
          </Button>
          <Button size={btn} variant="secondary" title="Pause" onClick={run(pause, "Pause")} aria-label="Pause">
            <Pause />
          </Button>
          <Button size={btn} variant="secondary" title="Stop" onClick={run(stop, "Stop")} aria-label="Stop">
            <Square />
          </Button>
        </>
      )}

      {group === "paused" && (
        <>
          <Button size={btn} onClick={run(unpause, "Resume")}>
            <Play /> Resume
          </Button>
          <Button size={btn} variant="secondary" title="Stop" onClick={run(stop, "Stop")}>
            <Square />
          </Button>
        </>
      )}

      {(group === "stopped" || group === "error") && (
        <Button size={btn} onClick={run(start, "Start")}>
          <Play /> Start
        </Button>
      )}

      {group === "transition" && (
        <Button size={btn} variant="secondary" disabled>
          {label}…
        </Button>
      )}

      <Button
        size={btn}
        variant="ghost"
        className="text-destructive hover:text-destructive"
        title="Destroy"
        onClick={() => setConfirmOpen(true)}
        aria-label="Destroy"
      >
        <Trash2 />
      </Button>

      <ConfirmDialog
        open={confirmOpen}
        onOpenChange={setConfirmOpen}
        title={`Destroy "${instance.name}"?`}
        description="This permanently removes the container. Named volumes are kept."
        confirmLabel="Destroy"
        variant="destructive"
        confirmPhrase={instance.name}
        extra={
          <div className="space-y-2 rounded-md border border-border p-2.5">
            <label className="flex items-center gap-2 text-xs text-muted-foreground">
              <input
                type="checkbox"
                checked={removeImage}
                onChange={(e) => setRemoveImage(e.target.checked)}
                className="accent-destructive"
              />
              Also remove the container image (only if no other instance uses it)
            </label>
            <label className="flex items-center gap-2 text-xs text-muted-foreground">
              <input
                type="checkbox"
                checked={removeTemplate}
                onChange={(e) => setRemoveTemplate(e.target.checked)}
                className="accent-destructive"
              />
              Also delete the template (only if no other instance uses it)
            </label>
          </div>
        }
        onConfirm={doDestroy}
      />
    </div>
  );
}
