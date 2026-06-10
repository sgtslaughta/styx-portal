import { useState } from "react";
import { Gauge } from "@/components/common/stat-tile";
import { OverlaySparkline } from "./sparkline";
import { RegistryInfo } from "./registry-info";
import { InstanceThumbnail } from "./instance-thumbnail";
import { StatusBadge } from "./status-badge";
import { ActionBar } from "@/components/common/action-bar";
import { LaunchConfigFields } from "@/components/templates/launch-config-fields";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { formatDuration, linuxserverImageName } from "@/lib/utils";
import { CHART_COLORS } from "@/lib/chart";
import { Save, AlertTriangle } from "lucide-react";
import { toast } from "sonner";
import {
  useInstances,
  useInstanceStats,
  useStartInstance,
  useStopInstance,
  useUpdateInstance,
  useRecreateInstance,
  useKeepalive,
} from "@/hooks/use-instances";
import { useTemplates, useUpdateTemplate } from "@/hooks/use-templates";
import { useGpuInfo } from "@/hooks/use-gpu";
import { useRegistryImage } from "@/hooks/use-registry";
import { useLaunchConfig } from "@/hooks/use-launch-config";

interface InstanceDetailPaneProps {
  instanceId: string | null;
}

export function InstanceDetailPane({ instanceId }: InstanceDetailPaneProps) {
  const { data: instances } = useInstances();
  const { data: templates } = useTemplates();
  const { data: gpuInfo } = useGpuInfo();
  const start = useStartInstance();
  const stop = useStopInstance();
  const update = useUpdateInstance();
  const recreate = useRecreateInstance();
  const updateTemplate = useUpdateTemplate();
  const keepalive = useKeepalive();

  const [showConfirmRebuild, setShowConfirmRebuild] = useState(false);

  // Resolve instance and template
  const instance = instances?.find((i) => i.id === instanceId) ?? null;
  const template = instance ? templates?.find((t) => t.id === instance.template_id) ?? null : null;

  // Session config for idle timeout notice
  const sc = instance?.session_config as { idle_timeout?: string; never_timeout?: boolean } | null;
  const hasTimeout = !!(sc && !sc.never_timeout && sc.idle_timeout);

  // Registry image lookup
  const lsName = template ? linuxserverImageName(template.image) : null;
  const { data: regImg } = useRegistryImage(lsName);

  // Initialize launch config (remounts per instanceId due to key in parent)
  const cfg = useLaunchConfig({ template: template ?? undefined, instance: instance ?? undefined });

  // Stats for running instances
  const isRunning = instance?.status === "running" || instance?.status === "idle";
  const { data: stats } = useInstanceStats(instanceId ?? "", !!instanceId && isRunning);

  // Compute diffs to detect changes
  const computeChanges = () => {
    if (!instance || !template) return { inPlaceChanged: false, templateChanged: false };

    // In-place changes: name, env, or session config
    const nameChanged = cfg.name !== instance.name;
    const templateEnv = { ...template.env_vars, ...instance.env_overrides };
    const envChanged = JSON.stringify(cfg.envVars) !== JSON.stringify(templateEnv);
    const sessionChanged =
      JSON.stringify({
        idle_timeout: cfg.idleTimeout,
        grace_period: cfg.gracePeriod,
      }) !==
      JSON.stringify({
        idle_timeout: instance.session_config?.idle_timeout ?? "30m",
        grace_period: instance.session_config?.grace_period ?? "5m",
      });
    const inPlaceChanged = nameChanged || envChanged || sessionChanged;

    // Template-level changes (recreate required). Normalize nullable string/number
    // fields so an empty-vs-null mismatch doesn't spuriously flag a change.
    const built = cfg.buildTemplateData();
    const s = (v: unknown) => v ?? "";
    const n = (v: unknown) => v ?? 0;
    const templateChanged =
      s(built.image) !== s(template.image) ||
      s(built.icon) !== s(template.icon) ||
      s(built.memory_limit) !== s(template.memory_limit) ||
      s(built.cpu_limit) !== s(template.cpu_limit) ||
      s(built.shm_size) !== s(template.shm_size) ||
      n(built.internal_port) !== n(template.internal_port) ||
      JSON.stringify(built.volumes ?? []) !== JSON.stringify(template.volumes ?? []) ||
      built.gpu_enabled !== template.gpu_enabled ||
      n(built.gpu_count) !== n(template.gpu_count);

    return { inPlaceChanged, templateChanged };
  };

  const { inPlaceChanged, templateChanged } = computeChanges();
  const isDirty = inPlaceChanged || templateChanged;

  const handleSave = async () => {
    if (!instance || !template) return;

    try {
      if (templateChanged) {
        // Rebuild path: update template, then recreate container
        const builtData = cfg.buildTemplateData();
        await updateTemplate.mutateAsync({ id: template.id, data: builtData });
        await recreate.mutateAsync(instance.id);
        toast.success("Template updated & container recreated");
        return;
      }

      if (inPlaceChanged) {
        // In-place path: reuse old instance-detail logic
        const data: Record<string, unknown> = {};

        if (cfg.name !== instance.name) data.name = cfg.name;

        const templateEnv = { ...template.env_vars, ...instance.env_overrides };
        const envChanged = JSON.stringify(cfg.envVars) !== JSON.stringify(templateEnv);
        if (envChanged) data.env_overrides = cfg.envVars;

        const sessionConfig = {
          idle_timeout: cfg.idleTimeout,
          grace_period: cfg.gracePeriod,
          timeout_action: instance.session_config?.timeout_action ?? "stop",
          never_timeout: instance.session_config?.never_timeout ?? false,
          max_session_duration: instance.session_config?.max_session_duration ?? null,
        };
        const configChanged =
          JSON.stringify(sessionConfig) !== JSON.stringify(instance.session_config);
        if (configChanged) data.session_config = sessionConfig;

        if (Object.keys(data).length === 0) {
          toast.info("No changes to save");
          return;
        }

        const needsRestart = isRunning && (envChanged || !!data.name);

        if (needsRestart) {
          // Stop → Update → Start
          stop.mutate(instance.id, {
            onSuccess: () => {
              update.mutate(
                { id: instance.id, data },
                {
                  onSuccess: () => {
                    start.mutate(instance.id, {
                      onSuccess: () => {
                        toast.success("Saved & restarted");
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
            { id: instance.id, data },
            {
              onSuccess: () => {
                toast.success("Settings saved");
              },
              onError: (e) => toast.error(`Update failed: ${e.message}`),
            }
          );
        }
      }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Save failed");
    }
  };

  if (!instanceId || !instance) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-2 text-center text-sm text-muted-foreground">
        <p>No instance selected.</p>
        <p>Pick one from the list, or launch a new one from the Template Gallery.</p>
      </div>
    );
  }

  const uptimeSeconds = instance.started_at && isRunning
    ? (Date.now() - new Date(instance.started_at + "Z").getTime()) / 1000
    : null;
  const idleSeconds = instance.last_activity && isRunning
    ? (Date.now() - new Date(instance.last_activity + "Z").getTime()) / 1000
    : null;

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Header: name + status + action bar */}
      <div className="flex-shrink-0 p-4 border-b border-border space-y-3">
        <div className="flex items-center justify-between gap-3">
          <h2 className="text-lg font-semibold truncate" title={instance.name}>{instance.name}</h2>
          <StatusBadge status={instance.status} showIcon />
        </div>
        <ActionBar instance={instance} />
      </div>

      {/* Content scroll area */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {/* Top: two equal-height columns — left info, right live preview */}
        <div className="grid grid-cols-2 gap-4 items-stretch">
          {/* Left: resources + graphs + LinuxServer.io details */}
          <div className="space-y-4 min-w-0">
            {/* Resources: live CPU/RAM gauges + sparkline */}
            {isRunning && stats && (
              <div className="space-y-3">
                <h3 className="text-xs font-semibold text-muted-foreground uppercase">Resources</h3>
                <div className="space-y-2">
                  <Gauge
                    value={stats.cpu_percent}
                    max={100}
                    label="CPU"
                    color={CHART_COLORS.cpu}
                  />
                  <Gauge
                    value={stats.memory_percent}
                    max={100}
                    label="Memory"
                    color={CHART_COLORS.memory}
                  />
                </div>
                {/* Sparkline with history */}
                <div className="rounded border border-border bg-card/50 p-2">
                  <OverlaySparkline
                    series={[
                      { value: stats.cpu_percent, color: CHART_COLORS.cpu, label: "CPU" },
                      { value: stats.memory_percent, color: CHART_COLORS.memory, label: "RAM" },
                    ]}
                    max={100}
                    height={40}
                  />
                </div>
                {/* Uptime + idle */}
                <div className="grid grid-cols-2 gap-2 text-xs">
                  <div className="rounded border border-border bg-card/50 p-2">
                    <div className="text-muted-foreground">Uptime</div>
                    <div className="font-mono text-sm">{formatDuration(uptimeSeconds)}</div>
                  </div>
                  <div className="rounded border border-border bg-card/50 p-2">
                    <div className="text-muted-foreground">Idle</div>
                    <div className="font-mono text-sm">{formatDuration(idleSeconds)}</div>
                  </div>
                </div>

                {/* Idle auto-stop notice + keep-awake button */}
                {hasTimeout && (
                  <div className="flex items-center gap-2 text-xs text-muted-foreground">
                    <span>Auto-stops when idle ({sc!.idle_timeout}).</span>
                    <Button
                      size="sm"
                      variant="secondary"
                      className="h-6 text-xs"
                      disabled={keepalive.isPending}
                      onClick={() => keepalive.mutate(instance.id)}
                    >
                      {keepalive.isPending ? "Keeping awake…" : "Keep awake"}
                    </Button>
                  </div>
                )}
              </div>
            )}

            {/* Registry info */}
            {regImg && (
              <div>
                <h3 className="text-xs font-semibold text-muted-foreground uppercase mb-3">LinuxServer.io</h3>
                <RegistryInfo image={regImg} />
              </div>
            )}
          </div>

          {/* Right: live preview, height-matched to the left column */}
          <InstanceThumbnail
            instanceId={instance.id}
            icon={template?.icon ?? null}
            isLive={isRunning}
            fill
          />
        </div>

        <Separator />

        {/* Config editor (full width) */}
        <div>
          <h3 className="text-xs font-semibold text-muted-foreground uppercase mb-3">Configuration</h3>
          <LaunchConfigFields cfg={cfg} gpuInfo={gpuInfo} />
        </div>
      </div>

      {/* Footer: Save button or restart confirm */}
      <div className="flex-shrink-0 border-t border-border p-4 space-y-3">
        {showConfirmRebuild && (
          <div className="rounded-lg border border-destructive/50 bg-destructive/10 p-3 space-y-2">
            <div className="flex items-center gap-2 text-destructive text-sm font-medium">
              <AlertTriangle className="h-4 w-4" />
              Rebuild Container?
            </div>
            <p className="text-xs text-muted-foreground">
              Updates the template and rebuilds the container with the new settings. The session restarts briefly. Persistent named volumes are kept — data is preserved.
            </p>
            <div className="flex gap-2">
              <Button
                size="sm"
                variant="destructive"
                onClick={async () => {
                  setShowConfirmRebuild(false);
                  try {
                    const builtData = cfg.buildTemplateData();
                    await updateTemplate.mutateAsync({ id: template!.id, data: builtData });
                    await recreate.mutateAsync(instance.id);
                    toast.success("Template updated & container recreated");
                  } catch (err) {
                    toast.error(err instanceof Error ? err.message : "Rebuild failed");
                  }
                }}
              >
                Rebuild
              </Button>
              <Button
                size="sm"
                variant="ghost"
                onClick={() => setShowConfirmRebuild(false)}
              >
                Cancel
              </Button>
            </div>
          </div>
        )}

        {!showConfirmRebuild && isDirty && (
          <Button
            onClick={() => {
              if (templateChanged) {
                setShowConfirmRebuild(true);
              } else {
                handleSave();
              }
            }}
            className="w-full gap-1.5"
          >
            <Save className="h-4 w-4" />
            Save Changes
          </Button>
        )}
      </div>
    </div>
  );
}
