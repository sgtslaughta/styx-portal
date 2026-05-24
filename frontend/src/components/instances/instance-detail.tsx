import { useState, useEffect } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Separator } from "@/components/ui/separator";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { StatusBadge } from "./status-badge";
import { EnvEditor } from "@/components/templates/env-editor";
import { formatDuration } from "@/lib/utils";
import {
  useStartInstance,
  useStopInstance,
  usePauseInstance,
  useUnpauseInstance,
  useDeleteInstance,
  useUpdateInstance,
} from "@/hooks/use-instances";
import { toast } from "sonner";
import {
  ExternalLink,
  Play,
  Square,
  Pause,
  Trash2,
  Save,
  AlertTriangle,
  Settings2,
  Info,
} from "lucide-react";
import type { Instance } from "@/lib/types";

interface InstanceDetailProps {
  instance: Instance | null;
  onClose: () => void;
}

export function InstanceDetail({ instance, onClose }: InstanceDetailProps) {
  const start = useStartInstance();
  const stop = useStopInstance();
  const pauseInst = usePauseInstance();
  const unpauseInst = useUnpauseInstance();
  const destroy = useDeleteInstance();
  const update = useUpdateInstance();

  const [name, setName] = useState("");
  const [envVars, setEnvVars] = useState<Record<string, string>>({});
  const [idleTimeout, setIdleTimeout] = useState("30m");
  const [gracePeriod, setGracePeriod] = useState("5m");
  const [timeoutAction, setTimeoutAction] = useState("stop");
  const [neverTimeout, setNeverTimeout] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [showRestartConfirm, setShowRestartConfirm] = useState(false);

  useEffect(() => {
    if (!instance) return;
    setName(instance.name);
    setEnvVars(instance.env_overrides ?? {});
    setIdleTimeout(instance.session_config?.idle_timeout ?? "30m");
    setGracePeriod(instance.session_config?.grace_period ?? "5m");
    setTimeoutAction(instance.session_config?.timeout_action ?? "stop");
    setNeverTimeout(instance.session_config?.never_timeout ?? false);
    setDirty(false);
    setShowRestartConfirm(false);
  }, [instance]);

  if (!instance) return null;

  const isRunning = instance.status === "running" || instance.status === "idle";
  const isPaused = instance.status === "paused";
  const idleSeconds = instance.last_activity
    ? (Date.now() - new Date(instance.last_activity + "Z").getTime()) / 1000
    : null;
  const uptimeSeconds = instance.started_at
    ? (Date.now() - new Date(instance.started_at + "Z").getTime()) / 1000
    : null;

  function markDirty() {
    setDirty(true);
  }

  function handleSave() {
    if (isRunning) {
      setShowRestartConfirm(true);
      return;
    }
    doSave();
  }

  function doSave() {
    setShowRestartConfirm(false);
    const data: Record<string, unknown> = {};
    if (name !== instance!.name) data.name = name;

    const envChanged =
      JSON.stringify(envVars) !== JSON.stringify(instance!.env_overrides ?? {});
    if (envChanged) data.env_overrides = envVars;

    const sessionConfig = {
      idle_timeout: idleTimeout,
      grace_period: gracePeriod,
      timeout_action: timeoutAction,
      never_timeout: neverTimeout,
      max_session_duration: instance!.session_config?.max_session_duration ?? null,
    };
    const configChanged =
      JSON.stringify(sessionConfig) !== JSON.stringify(instance!.session_config);
    if (configChanged) data.session_config = sessionConfig;

    if (Object.keys(data).length === 0) {
      toast.info("No changes to save");
      return;
    }

    const needsRestart = isRunning && (envChanged || !!data.name);

    if (needsRestart) {
      stop.mutate(instance!.id, {
        onSuccess: () => {
          update.mutate(
            { id: instance!.id, data },
            {
              onSuccess: () => {
                start.mutate(instance!.id, {
                  onSuccess: () => {
                    toast.success("Saved & restarted");
                    setDirty(false);
                  },
                  onError: (e) => toast.error(`Restart failed: ${e.message}`),
                });
              },
              onError: (e) => toast.error(`Update failed: ${e.message}`),
            }
          );
        },
        onError: (e) => toast.error(`Stop failed: ${e.message}`),
      });
    } else {
      update.mutate(
        { id: instance!.id, data },
        {
          onSuccess: () => {
            toast.success("Settings saved");
            setDirty(false);
          },
          onError: (e) => toast.error(`Update failed: ${e.message}`),
        }
      );
    }
  }

  function handleDestroy() {
    if (!confirm(`Destroy "${instance!.name}"? This removes the container.`))
      return;
    destroy.mutate(
      { id: instance!.id, removeVolumes: false },
      {
        onSuccess: () => {
          toast.success("Instance destroyed");
          onClose();
        },
        onError: (e) => toast.error(`Destroy failed: ${e.message}`),
      }
    );
  }

  return (
    <Dialog open={!!instance} onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="max-h-[90vh] w-[90vw] max-w-2xl overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-3">
            {instance.name}
            <StatusBadge status={instance.status} />
          </DialogTitle>
        </DialogHeader>

        {/* Status row */}
        <div className="grid grid-cols-3 gap-3 text-sm">
          <div>
            <span className="text-muted-foreground text-xs">Subdomain</span>
            <div className="mt-0.5 font-mono text-xs">{instance.subdomain}</div>
          </div>
          {isRunning && (
            <>
              <div>
                <span className="text-muted-foreground text-xs">Uptime</span>
                <div className="mt-0.5 text-xs">{formatDuration(uptimeSeconds)}</div>
              </div>
              <div>
                <span className="text-muted-foreground text-xs">Idle</span>
                <div className="mt-0.5 text-xs">{formatDuration(idleSeconds)}</div>
              </div>
            </>
          )}
        </div>

        <Separator />

        {/* Editable tabs */}
        <Tabs defaultValue="general" className="w-full">
          <TabsList className="w-full grid grid-cols-3 gap-1 p-1">
            <TabsTrigger value="general" className="text-xs gap-1.5">
              <Settings2 className="h-3.5 w-3.5" />
              General
            </TabsTrigger>
            <TabsTrigger value="env" className="text-xs gap-1.5">
              <Info className="h-3.5 w-3.5" />
              Environment
            </TabsTrigger>
            <TabsTrigger value="session" className="text-xs gap-1.5">
              <Settings2 className="h-3.5 w-3.5" />
              Session
            </TabsTrigger>
          </TabsList>

          <TabsContent value="general" className="space-y-3 mt-4">
            <div>
              <Label>Instance Name</Label>
              <Input
                value={name}
                onChange={(e) => {
                  setName(e.target.value);
                  markDirty();
                }}
              />
            </div>
            <div className="grid grid-cols-2 gap-3 text-xs text-muted-foreground">
              <div>
                <span>Template ID</span>
                <div className="mt-0.5 font-mono">{instance.template_id.slice(0, 8)}...</div>
              </div>
              <div>
                <span>Instance ID</span>
                <div className="mt-0.5 font-mono">{instance.id.slice(0, 8)}...</div>
              </div>
            </div>
            {instance.volume_names.length > 0 && (
              <div>
                <Label className="text-xs text-muted-foreground">Volumes (persistent)</Label>
                <div className="mt-1 space-y-1">
                  {instance.volume_names.map((v) => (
                    <div key={v} className="rounded bg-secondary px-2 py-1 font-mono text-xs">
                      {v}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </TabsContent>

          <TabsContent value="env" className="mt-4">
            <EnvEditor
              value={envVars}
              onChange={(v) => {
                setEnvVars(v);
                markDirty();
              }}
            />
          </TabsContent>

          <TabsContent value="session" className="space-y-3 mt-4">
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label>Idle Timeout</Label>
                <Input
                  value={idleTimeout}
                  onChange={(e) => {
                    setIdleTimeout(e.target.value);
                    markDirty();
                  }}
                />
              </div>
              <div>
                <Label>Grace Period</Label>
                <Input
                  value={gracePeriod}
                  onChange={(e) => {
                    setGracePeriod(e.target.value);
                    markDirty();
                  }}
                />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label>Timeout Action</Label>
                <select
                  value={timeoutAction}
                  onChange={(e) => {
                    setTimeoutAction(e.target.value);
                    markDirty();
                  }}
                  className="mt-1 h-9 w-full rounded-md border border-input bg-background px-3 text-sm"
                >
                  <option value="stop">Stop</option>
                  <option value="destroy">Destroy</option>
                </select>
              </div>
              <div className="flex items-end gap-3 pb-1">
                <Switch
                  checked={neverTimeout}
                  onCheckedChange={(v) => {
                    setNeverTimeout(v);
                    markDirty();
                  }}
                />
                <Label className="text-sm">Never Timeout</Label>
              </div>
            </div>
          </TabsContent>
        </Tabs>

        {/* Restart warning dialog */}
        {showRestartConfirm && (
          <>
            <Separator />
            <div className="rounded-lg border border-yellow-500/50 bg-yellow-500/10 p-3 space-y-2">
              <div className="flex items-center gap-2 text-yellow-600 text-sm font-medium">
                <AlertTriangle className="h-4 w-4" />
                Restart Required
              </div>
              <p className="text-xs text-muted-foreground">
                Changing environment variables or name on a running instance requires a restart.
                The container will be stopped, settings applied, and a new container started with your existing volumes.
              </p>
              <div className="flex gap-2">
                <Button size="sm" onClick={doSave} className="gap-1.5">
                  <Play className="h-3 w-3" />
                  Save & Restart
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => setShowRestartConfirm(false)}
                >
                  Cancel
                </Button>
              </div>
            </div>
          </>
        )}

        <Separator />

        {/* Actions */}
        <div className="flex gap-2">
          {dirty && !showRestartConfirm && (
            <Button onClick={handleSave} className="flex-1 gap-1.5">
              <Save className="h-3 w-3" />
              {isRunning ? "Save (requires restart)" : "Save"}
            </Button>
          )}
          {!dirty && isRunning && (
            <Button
              className="flex-1"
              onClick={() =>
                window.open(`/i/${instance.subdomain}/`, "_blank")
              }
            >
              <ExternalLink className="mr-2 h-3 w-3" /> Connect
            </Button>
          )}
          {isRunning && (
            <>
              <Button
                variant="secondary"
                onClick={() => pauseInst.mutate(instance.id, { onError: (e) => toast.error(e.message) })}
              >
                <Pause className="mr-2 h-3 w-3" /> Pause
              </Button>
              <Button
                variant="secondary"
                onClick={() => stop.mutate(instance.id, { onError: (e) => toast.error(e.message) })}
              >
                <Square className="mr-2 h-3 w-3" /> Stop
              </Button>
            </>
          )}
          {isPaused && (
            <>
              <Button
                className="flex-1"
                onClick={() => unpauseInst.mutate(instance.id, { onError: (e) => toast.error(e.message) })}
              >
                <Play className="mr-2 h-3 w-3" /> Resume
              </Button>
              <Button
                variant="secondary"
                onClick={() => stop.mutate(instance.id, { onError: (e) => toast.error(e.message) })}
              >
                <Square className="mr-2 h-3 w-3" /> Stop
              </Button>
            </>
          )}
          {!isRunning && !isPaused && !dirty && (
            <Button
              className="flex-1"
              onClick={() => start.mutate(instance.id, { onError: (e) => toast.error(e.message) })}
            >
              <Play className="mr-2 h-3 w-3" /> Start
            </Button>
          )}
          <Button variant="destructive" onClick={handleDestroy}>
            <Trash2 className="mr-2 h-3 w-3" /> Destroy
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
