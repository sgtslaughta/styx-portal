import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Glyph } from "./glyph";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { EnvEditor } from "@/components/templates/env-editor";
import { StorageSection } from "@/components/templates/builder/sections/storage";
import { PortsNetworkSection } from "@/components/templates/builder/sections/ports-network";
import { useWaveTransition } from "@/components/effects/transition-provider";
import { useAuth } from "@/hooks/use-auth";
import { useCreateInstance } from "@/hooks/use-instances";
import { useCreateTemplate, useSizePresets } from "@/hooks/use-templates";
import { useLaunchConfig } from "@/hooks/use-launch-config";
import { profileMountOf } from "@/lib/profiles";
import { slugify } from "@/lib/utils";
import { resolveTemplate } from "./resolve-template";
import type { RegistryImage, ServiceTemplate, SessionConfig } from "@/lib/types";

export interface LaunchTarget { image?: RegistryImage; template?: ServiceTemplate; custom?: string }
type Idle = "stop" | "keep";

export function LaunchStep({ target, onClose }: { target: LaunchTarget; onClose: () => void }) {
  const { image, template, custom } = target;
  const cfg = useLaunchConfig({ registryImage: image, template });
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";
  const { data: presets = [] } = useSizePresets();
  const createInstance = useCreateInstance();
  const createTemplate = useCreateTemplate();
  const wave = useWaveTransition();
  const [presetId, setPresetId] = useState("standard");
  const [keepProfile, setKeepProfile] = useState(true);
  const [idle, setIdle] = useState<Idle>(template?.session_config?.never_timeout ? "keep" : "stop");
  const [saveSetup, setSaveSetup] = useState(false);
  const [busy, setBusy] = useState(false);
  const preset = presets.find((p) => p.id === presetId);
  const hasProfile = !!profileMountOf(cfg.profileMount, cfg.volumes);

  useEffect(() => {
    if (!custom) return;
    const n = custom.split("/").pop()!.replace(/[:@].*$/, "");
    cfg.setImage(custom); cfg.setName(n); cfg.setSubdomain(slugify(n)); cfg.setProfileMount("");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Presets size new containers; a saved setup keeps its own size.
  useEffect(() => {
    if (template || !preset) return;
    cfg.setCpuLimit(String(preset.cpus)); cfg.setMemoryLimit(`${preset.memory_gb}g`); cfg.setGpuEnabled(preset.gpu);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [preset?.id, template]);

  async function launch() {
    if (!cfg.name.trim() || !cfg.image.trim()) { toast.error("Name and image required"); return; }
    setBusy(true);
    try {
      const data = cfg.buildTemplateData();
      if (!template && preset) Object.assign(data, { cpu_limit: String(preset.cpus), memory_limit: `${preset.memory_gb}g`, gpu_enabled: preset.gpu, gpu_count: preset.gpu ? 1 : 0 });
      const tmpl = await resolveTemplate({ template, data, create: createTemplate.mutateAsync, regName: image?.name, userId: user?.id, isAdmin });
      const sc: SessionConfig = { ...(template?.session_config ?? data.session_config), timeout_action: "stop", never_timeout: idle === "keep" };
      await createInstance.mutateAsync({
        template_id: tmpl.id, name: cfg.name, subdomain: cfg.subdomain, session_config: sc,
        use_profile: hasProfile && keepProfile, use_gpu: !template && preset ? preset.gpu : true,
      });
      if (saveSetup && isAdmin && !template) {
        await createTemplate.mutateAsync({ ...data, name: `${data.name}-setup`, display_name: `${cfg.name} setup`, shared: true })
          .catch((e) => toast.error(`Setup not saved: ${(e as Error).message}`));
      }
      onClose();
      wave.play(`Launching ${cfg.name}…`);
      toast.success(`Instance "${cfg.name}" launched!`);
    } catch (e) {
      toast.error(`Launch failed: ${(e as Error).message}`);
    } finally { setBusy(false); }
  }

  return (
    <>
      <div className="flex-1 overflow-y-auto px-6 py-5">
        <div className="grid max-w-[560px] gap-[18px]">
          <div className="flex items-center gap-3.5">
            <Glyph name={cfg.name || "?"} icon={cfg.icon} size={52} />
            <div className="min-w-0"><strong className="block text-lg">{image?.name ?? template?.display_name ?? cfg.name}</strong><div className="truncate text-[13.5px] text-muted-foreground">{cfg.image}</div></div>
          </div>
          <label className="grid gap-1.5 text-sm font-medium">Name
            <Input value={cfg.name} onChange={(e) => { cfg.setName(e.target.value); cfg.setSubdomain(slugify(e.target.value)); }} />
          </label>
          {template ? (
            <p className="text-sm text-muted-foreground">Size comes from this setup: {template.cpu_limit ?? "default"} cores, {template.memory_limit ?? "default"}{template.gpu_enabled ? ", GPU" : ""}.</p>
          ) : (
            <div>
              <div className="mb-1.5 text-sm font-medium">Size</div>
              <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
                {presets.map((p) => (
                  <button key={p.id} type="button" aria-pressed={p.id === presetId} onClick={() => setPresetId(p.id)}
                    className="rounded-[10px] border border-border bg-card p-2.5 text-left text-[13px] text-muted-foreground aria-pressed:border-transparent aria-pressed:shadow-[0_0_0_1.5px_#C9A04E]">
                    <strong className="block text-sm text-foreground">{p.label}</strong>{p.cpus} cores, {p.memory_gb} GB{p.gpu ? ", GPU" : ""}
                  </button>
                ))}
              </div>
            </div>
          )}
          {hasProfile && (
            <label className="flex items-center gap-2 text-sm"><input type="checkbox" className="size-4 accent-primary" checked={keepProfile} onChange={(e) => setKeepProfile(e.target.checked)} /> Keep my profile between sessions</label>
          )}
          <label className="grid gap-1.5 text-sm font-medium">When idle
            <select value={idle} onChange={(e) => setIdle(e.target.value as Idle)} className="rounded-lg border border-border bg-card px-3 py-2">
              <option value="stop">Stop after 30 min</option>
              <option value="keep">Keep running</option>
            </select>
          </label>
          <details>
            <summary className="cursor-pointer text-sm text-muted-foreground">Advanced: environment, volumes, ports</summary>
            <div className="mt-2 space-y-4">
              {image && <p className="text-[13px] text-muted-foreground">Prefilled from the LinuxServer image docs.</p>}
              <EnvEditor value={cfg.envVars} onChange={cfg.setEnvVars} descriptions={cfg.envDescriptions} />
              <StorageSection cfg={cfg} isAdmin={isAdmin} />
              <PortsNetworkSection cfg={cfg} isAdmin={isAdmin} />
            </div>
          </details>
          {isAdmin && !template && (
            <label className="flex items-center gap-2 text-sm"><input type="checkbox" className="size-4 accent-primary" checked={saveSetup} onChange={(e) => setSaveSetup(e.target.checked)} /> Save as a setup for one-click launch</label>
          )}
        </div>
      </div>
      <div className="flex justify-end gap-2.5 border-t border-border px-6 py-3.5">
        <Button variant="secondary" onClick={onClose}>Cancel</Button>
        <button type="button" className="btn-gold" onClick={launch} disabled={busy}>{busy ? "Launching…" : "Launch"}</button>
      </div>
    </>
  );
}
