import { useState, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Drawer, DrawerContent, DrawerHeader, DrawerBody, DrawerFooter,
  DrawerTitle,
} from "@/components/ui/drawer";
import { StatusBadge } from "./status-badge";
import { GeneralTab, SessionTab } from "./detail-tabs";
import { EnvEditor } from "@/components/templates/env-editor";
import { ActionBar } from "@/components/common/action-bar";
import { formatDuration } from "@/lib/utils";
import {
  useInstances,
  useStartInstance,
  useStopInstance,
  useUpdateInstance,
} from "@/hooks/use-instances";
import { toast } from "sonner";
import {
  Play,
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
  const { data: instances } = useInstances();
  const start = useStartInstance();
  const stop = useStopInstance();
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

  // Close the drawer when the open instance is destroyed (vanishes from the query).
  useEffect(() => {
    if (instance && instances && !instances.some((i) => i.id === instance.id)) {
      onClose();
    }
  }, [instances, instance, onClose]);

  if (!instance) return null;

  const isRunning = instance.status === "running" || instance.status === "idle";
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

  return (
    <Drawer open={!!instance} onOpenChange={(v) => !v && onClose()}>
      <DrawerContent>
        <DrawerHeader>
          <DrawerTitle className="flex items-center gap-3">
            {instance.name}
            <StatusBadge status={instance.status} />
          </DrawerTitle>
        </DrawerHeader>

        <DrawerBody className="space-y-4">

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
              <GeneralTab instance={instance} name={name} setName={setName} markDirty={markDirty} />
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
              <SessionTab
                idleTimeout={idleTimeout}
                setIdleTimeout={setIdleTimeout}
                gracePeriod={gracePeriod}
                setGracePeriod={setGracePeriod}
                timeoutAction={timeoutAction}
                setTimeoutAction={setTimeoutAction}
                neverTimeout={neverTimeout}
                setNeverTimeout={setNeverTimeout}
                markDirty={markDirty}
              />
            </TabsContent>
          </Tabs>

          {/* Restart warning dialog */}
          {showRestartConfirm && (
            <>
              <Separator />
              <div className="rounded-lg border border-warning/50 bg-warning/10 p-3 space-y-2">
                <div className="flex items-center gap-2 text-warning text-sm font-medium">
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
        </DrawerBody>

        <DrawerFooter>
          {dirty && !showRestartConfirm && (
            <Button onClick={handleSave} className="gap-1.5">
              <Save className="h-3 w-3" />
              {isRunning ? "Save (requires restart)" : "Save"}
            </Button>
          )}
          {!dirty && (
            <ActionBar instance={instance} />
          )}
        </DrawerFooter>
      </DrawerContent>
    </Drawer>
  );
}
