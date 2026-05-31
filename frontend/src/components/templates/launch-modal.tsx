import { useState } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { EnvEditor } from "./env-editor";
import { GpuIndicator } from "./launch-gpu-indicator";
import { SelkiesSettings } from "./launch-selkies-settings";
import { useCreateTemplate, useUpdateTemplate } from "@/hooks/use-templates";
import { useCreateInstance } from "@/hooks/use-instances";
import { useGpuInfo } from "@/hooks/use-gpu";
import { slugify } from "@/lib/utils";
import { api } from "@/api/client";
import { toast } from "sonner";
import { Plus, Trash2, Shield, HardDrive, Network, Settings2, Info, ExternalLink, Monitor } from "lucide-react";
import type { RegistryImage, ServiceTemplate } from "@/lib/types";

interface LaunchModalProps {
  open: boolean;
  onClose: () => void;
  registryImage?: RegistryImage | null;
  template?: ServiceTemplate | null;
}

interface VolumeEntry { name: string; mount: string; desc?: string }
interface PortEntry { internal: string; external: string; desc?: string }
interface SecurityOpt { value: string; desc?: string; enabled: boolean }
interface CustomOpt { name: string; value: string; desc?: string }

export function LaunchModal({ open, onClose, registryImage, template }: LaunchModalProps) {
  const createTemplate = useCreateTemplate();
  const updateTemplate = useUpdateTemplate();
  const createInstance = useCreateInstance();
  const { data: gpuInfo } = useGpuInfo();

  const prefillName = registryImage?.name ?? template?.display_name ?? "";
  const registryTag = registryImage?.tags?.[0]?.tag ?? "latest";
  const prefillImage = registryImage ? `lscr.io/linuxserver/${registryImage.name}:${registryTag}` : template?.image ?? "";

  // Env vars with descriptions
  const prefillEnv: Record<string, string> = {};
  const envDescriptions: Record<string, string> = {};
  if (registryImage?.config?.env_vars) {
    for (const v of registryImage.config.env_vars) {
      prefillEnv[v.name] = v.value ?? "";
      envDescriptions[v.name] = v.desc ?? "";
    }
  } else if (template?.env_vars) {
    Object.assign(prefillEnv, template.env_vars);
  }

  // Volumes
  const prefillVolumes: VolumeEntry[] = [];
  if (registryImage?.config?.volumes) {
    for (const v of registryImage.config.volumes) {
      prefillVolumes.push({ name: `{instance_id}${v.path.replace(/\//g, "-")}`, mount: v.path, desc: v.desc });
    }
  } else if (template?.volumes) {
    prefillVolumes.push(...template.volumes);
  }

  // Ports
  const prefillPorts: PortEntry[] = [];
  if (registryImage?.config?.ports) {
    for (const p of registryImage.config.ports) {
      prefillPorts.push({ internal: p.internal, external: p.external, desc: p.desc });
    }
  }

  // Security options
  const prefillSecurity: SecurityOpt[] = [];
  if (registryImage?.config?.security_opt) {
    for (const s of registryImage.config.security_opt) {
      prefillSecurity.push({ value: s.compose_var, desc: s.desc, enabled: !s.optional });
    }
  }

  // Custom docker options (shm_size, etc)
  const prefillCustom: CustomOpt[] = [];
  if (registryImage?.config?.custom) {
    for (const c of registryImage.config.custom) {
      prefillCustom.push({ name: c.name_compose, value: c.value, desc: c.desc });
    }
  }

  // Determine shm from custom opts or template
  const shmFromCustom = prefillCustom.find(c => c.name === "shm_size");
  const defaultShm = shmFromCustom?.value ?? template?.shm_size ?? "1g";

  const [name, setName] = useState(prefillName);
  const [subdomain, setSubdomain] = useState(slugify(prefillName));
  const [image, setImage] = useState(prefillImage);
  const [icon, setIcon] = useState(registryImage?.project_logo ?? template?.icon ?? "");
  const [memoryLimit, setMemoryLimit] = useState(template?.memory_limit ?? "4g");
  const [cpuLimit, setCpuLimit] = useState(template?.cpu_limit ?? "2.0");
  const [envVars, setEnvVars] = useState(prefillEnv);
  const [gpuEnabled, setGpuEnabled] = useState(template?.gpu_enabled ?? (gpuInfo?.available ?? false));
  const [gpuDevices, setGpuDevices] = useState<string[]>([]);
  const [shmSize, setShmSize] = useState(defaultShm);
  const [volumes, setVolumes] = useState<VolumeEntry[]>(prefillVolumes);
  const [ports, setPorts] = useState<PortEntry[]>(prefillPorts);
  const [securityOpts, setSecurityOpts] = useState<SecurityOpt[]>(prefillSecurity);
  const [customOpts, setCustomOpts] = useState<CustomOpt[]>(prefillCustom.filter(c => c.name !== "shm_size"));
  const [idleTimeout, setIdleTimeout] = useState("30m");
  const [gracePeriod, setGracePeriod] = useState("5m");

  function isSelkiesImage(img: string): boolean {
    const lower = img.toLowerCase();
    return lower.includes("selkies") || lower.includes("kasmvnc");
  }

  function detectPortAndProtocol(img: string): { port: number; protocol: string } {
    if (template?.internal_port && template?.internal_protocol) {
      return { port: template.internal_port, protocol: template.internal_protocol };
    }
    if (isSelkiesImage(img)) return { port: 3001, protocol: "https" };
    // Standard linuxserver containers: nginx on 80 (HTTP) / 443 (HTTPS)
    return { port: 443, protocol: "https" };
  }

  function buildTemplateData() {
    const secOpts = securityOpts.filter(s => s.enabled).map(s => s.value);
    const { port: webPort, protocol: webProtocol } = detectPortAndProtocol(image);
    return {
      name: slugify(name),
      display_name: name,
      image,
      icon: icon || undefined,
      description: registryImage?.description ?? template?.description ?? "",
      env_vars: envVars,
      gpu_enabled: gpuEnabled,
      gpu_count: gpuEnabled ? (gpuDevices.length || 1) : 0,
      memory_limit: memoryLimit,
      cpu_limit: cpuLimit,
      shm_size: shmSize,
      volumes: volumes.map(v => ({ name: v.name, mount: v.mount })),
      internal_port: webPort,
      internal_protocol: webProtocol,
      category: registryImage?.category ?? template?.category ?? undefined,
      tags: [] as string[],
      session_config: { idle_timeout: idleTimeout, grace_period: gracePeriod, timeout_action: "stop" as const, never_timeout: false, max_session_duration: null },
      security_opts: secOpts.length > 0 ? secOpts : undefined,
      custom_opts: customOpts.length > 0 ? Object.fromEntries(customOpts.map(c => [c.name, c.value])) : undefined,
    };
  }

  async function upsertTemplate() {
    const templateData = buildTemplateData();
    try {
      return await createTemplate.mutateAsync(templateData);
    } catch {
      const templates = await api.listTemplates();
      const existing = templates.find((t) => t.name === slugify(name));
      if (!existing) throw new Error("Failed to create or find template");
      return await updateTemplate.mutateAsync({ id: existing.id, data: templateData });
    }
  }

  async function handleSaveAndLaunch() {
    if (!name.trim() || !image.trim()) { toast.error("Name and image required"); return; }
    try {
      const tmpl = await upsertTemplate();
      await createInstance.mutateAsync({ template_id: tmpl.id, name, subdomain });
      toast.success(`Instance "${name}" launched!`);
      onClose();
    } catch (e) {
      toast.error(`Launch failed: ${(e as Error).message}`);
    }
  }

  async function handleSaveTemplate() {
    if (!name.trim() || !image.trim()) { toast.error("Name and image required"); return; }
    try {
      await upsertTemplate();
      toast.success(`Template "${name}" saved!`);
      onClose();
    } catch (e) {
      toast.error(`Save failed: ${(e as Error).message}`);
    }
  }

  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="max-h-[90vh] w-[90vw] max-w-4xl overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-3">
            {icon && <img src={icon} alt="" className="h-8 w-8 rounded object-contain" />}
            {registryImage ? `Import: ${registryImage.name}` : template ? `Launch: ${template.display_name}` : "Custom Template"}
          </DialogTitle>
          {registryImage?.description && (
            <p className="text-xs text-muted-foreground line-clamp-2">{registryImage.description}</p>
          )}
        </DialogHeader>

        {/* Core fields */}
        <div className="space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <div><Label>Name</Label><Input value={name} onChange={(e) => { setName(e.target.value); setSubdomain(slugify(e.target.value)); }} /></div>
            <div><Label>Subdomain</Label><Input value={subdomain} onChange={(e) => setSubdomain(e.target.value)} className="font-mono text-sm" /></div>
          </div>
          <div className="grid grid-cols-[1fr_200px] gap-3">
            <div className="min-w-0"><Label>Docker Image</Label><Input value={image} onChange={(e) => setImage(e.target.value)} className="font-mono text-sm" /></div>
            <div className="min-w-0"><Label>Icon URL</Label><Input value={icon} onChange={(e) => setIcon(e.target.value)} placeholder="https://..." className="text-sm" /></div>
          </div>
        </div>

        <Separator />

        {/* GPU Indicator */}
        <GpuIndicator gpuInfo={gpuInfo} gpuEnabled={gpuEnabled} setGpuEnabled={setGpuEnabled} gpuDevices={gpuDevices} setGpuDevices={setGpuDevices} />

        <Separator />

        {/* Tabbed config sections */}
        <Tabs defaultValue="resources" className="w-full min-w-0 overflow-hidden">
          <TabsList className="w-full grid grid-cols-6 gap-1 p-1">
            <TabsTrigger value="resources" className="text-xs gap-1.5 px-3"><Settings2 className="h-3.5 w-3.5" />Resources</TabsTrigger>
            <TabsTrigger value="env" className="text-xs gap-1.5 px-3"><Info className="h-3.5 w-3.5" />Env</TabsTrigger>
            <TabsTrigger value="volumes" className="text-xs gap-1.5 px-3"><HardDrive className="h-3.5 w-3.5" />Volumes</TabsTrigger>
            <TabsTrigger value="network" className="text-xs gap-1.5 px-3"><Network className="h-3.5 w-3.5" />Ports</TabsTrigger>
            <TabsTrigger value="security" className="text-xs gap-1.5 px-3"><Shield className="h-3.5 w-3.5" />Security</TabsTrigger>
            <TabsTrigger value="selkies" className="text-xs gap-1.5 px-3"><Monitor className="h-3.5 w-3.5" />Selkies</TabsTrigger>
          </TabsList>

          <TabsContent value="resources" className="space-y-4 mt-4">
            <div className="grid grid-cols-3 gap-3">
              <div><Label>Memory</Label><Input value={memoryLimit} onChange={(e) => setMemoryLimit(e.target.value)} placeholder="4g" /></div>
              <div><Label>CPU</Label><Input value={cpuLimit} onChange={(e) => setCpuLimit(e.target.value)} placeholder="2.0" /></div>
              <div><Label>SHM Size</Label><Input value={shmSize} onChange={(e) => setShmSize(e.target.value)} placeholder="1g" /></div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div><Label>Idle Timeout</Label><Input value={idleTimeout} onChange={(e) => setIdleTimeout(e.target.value)} /></div>
              <div><Label>Grace Period</Label><Input value={gracePeriod} onChange={(e) => setGracePeriod(e.target.value)} /></div>
            </div>
            {/* Custom Docker Options */}
            {customOpts.length > 0 && (
              <div>
                <Label className="mb-2 block text-xs text-muted-foreground">Custom Docker Options</Label>
                {customOpts.map((opt, i) => (
                  <div key={i} className="mb-2 flex items-center gap-2 min-w-0">
                    <Input value={opt.name} onChange={(e) => { const n = [...customOpts]; n[i] = { ...opt, name: e.target.value }; setCustomOpts(n); }} placeholder="option" className="w-32 shrink-0 font-mono text-xs" />
                    <Input value={opt.value} onChange={(e) => { const n = [...customOpts]; n[i] = { ...opt, value: e.target.value }; setCustomOpts(n); }} placeholder="value" className="flex-1 min-w-0 font-mono text-xs" />
                    {opt.desc && <span className="text-[10px] text-muted-foreground max-w-40 truncate shrink-0" title={opt.desc}>{opt.desc}</span>}
                    <Button variant="ghost" size="icon" className="h-7 w-7 shrink-0" onClick={() => setCustomOpts(customOpts.filter((_, j) => j !== i))}><Trash2 className="h-3 w-3" /></Button>
                  </div>
                ))}
              </div>
            )}
            <Button variant="outline" size="sm" onClick={() => setCustomOpts([...customOpts, { name: "", value: "", desc: "" }])}>
              <Plus className="mr-1 h-3 w-3" /> Add Docker Option
            </Button>
          </TabsContent>

          <TabsContent value="env" className="mt-4">
            <EnvEditor value={envVars} onChange={setEnvVars} descriptions={envDescriptions} />
          </TabsContent>

          <TabsContent value="volumes" className="space-y-3 mt-4">
            {volumes.map((vol, i) => (
              <div key={i} className="flex items-start gap-2 min-w-0">
                <div className="flex-1 min-w-0">
                  <Input value={vol.name} onChange={(e) => { const n = [...volumes]; n[i] = { ...vol, name: e.target.value }; setVolumes(n); }} placeholder="volume-name" className="font-mono text-xs" />
                  {vol.desc && <p className="mt-0.5 text-[10px] text-muted-foreground truncate">{vol.desc}</p>}
                </div>
                <Input value={vol.mount} onChange={(e) => { const n = [...volumes]; n[i] = { ...vol, mount: e.target.value }; setVolumes(n); }} placeholder="/mount/path" className="flex-1 min-w-0 font-mono text-xs" />
                <Button variant="ghost" size="icon" className="h-9 w-9 shrink-0" onClick={() => setVolumes(volumes.filter((_, j) => j !== i))}><Trash2 className="h-3 w-3" /></Button>
              </div>
            ))}
            <Button variant="outline" size="sm" onClick={() => setVolumes([...volumes, { name: "", mount: "" }])}>
              <Plus className="mr-1 h-3 w-3" /> Add Volume
            </Button>
          </TabsContent>

          <TabsContent value="network" className="space-y-3 mt-4">
            <p className="text-[10px] text-muted-foreground mb-2">Selkies uses port 3001 (HTTPS) by default. Additional ports shown for reference.</p>
            {ports.map((port, i) => (
              <div key={i} className="flex items-start gap-2">
                <div className="flex-1">
                  <div className="flex gap-2">
                    <Input value={port.internal} onChange={(e) => { const n = [...ports]; n[i] = { ...port, internal: e.target.value }; setPorts(n); }} placeholder="container" className="w-20 font-mono text-xs" />
                    <span className="self-center text-xs text-muted-foreground">→</span>
                    <Input value={port.external} onChange={(e) => { const n = [...ports]; n[i] = { ...port, external: e.target.value }; setPorts(n); }} placeholder="host" className="w-20 font-mono text-xs" />
                  </div>
                  {port.desc && <p className="mt-0.5 text-[10px] text-muted-foreground">{port.desc}</p>}
                </div>
                <Button variant="ghost" size="icon" className="h-9 w-9" onClick={() => setPorts(ports.filter((_, j) => j !== i))}><Trash2 className="h-3 w-3" /></Button>
              </div>
            ))}
            <Button variant="outline" size="sm" onClick={() => setPorts([...ports, { internal: "", external: "" }])}>
              <Plus className="mr-1 h-3 w-3" /> Add Port
            </Button>
          </TabsContent>

          <TabsContent value="security" className="space-y-4 mt-4">
            {securityOpts.length > 0 && (
              <div className="space-y-2">
                {securityOpts.map((opt, i) => (
                  <div key={i} className="flex items-center gap-3 rounded-md border border-border p-2">
                    <Switch checked={opt.enabled} onCheckedChange={(v) => { const n = [...securityOpts]; n[i] = { ...opt, enabled: v }; setSecurityOpts(n); }} />
                    <div className="flex-1">
                      <code className="text-xs">{opt.value}</code>
                      {opt.desc && <p className="text-[10px] text-muted-foreground">{opt.desc}</p>}
                    </div>
                    <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => setSecurityOpts(securityOpts.filter((_, j) => j !== i))}><Trash2 className="h-3 w-3" /></Button>
                  </div>
                ))}
              </div>
            )}
            <Button variant="outline" size="sm" onClick={() => setSecurityOpts([...securityOpts, { value: "", desc: "", enabled: true }])}>
              <Plus className="mr-1 h-3 w-3" /> Add Security Option
            </Button>
            {securityOpts.length === 0 && (
              <p className="text-xs text-muted-foreground">No security options configured. Default: seccomp=unconfined, apparmor=unconfined applied automatically.</p>
            )}
          </TabsContent>

          <TabsContent value="selkies" className="mt-4">
            <SelkiesSettings envVars={envVars} onChange={setEnvVars} />
          </TabsContent>
        </Tabs>

        {/* Changelog preview */}
        {registryImage?.changelog && registryImage.changelog.length > 0 && (
          <>
            <Separator />
            <details className="text-xs">
              <summary className="cursor-pointer text-muted-foreground hover:text-foreground">Changelog ({registryImage.changelog.length} entries)</summary>
              <div className="mt-2 space-y-1 max-h-24 overflow-y-auto">
                {registryImage.changelog.map((entry, i) => (
                  <div key={i} className="flex gap-2">
                    <span className="text-muted-foreground shrink-0">{entry.date}</span>
                    <span>{entry.desc}</span>
                  </div>
                ))}
              </div>
            </details>
          </>
        )}

        {/* Setup link */}
        {registryImage?.config?.application_setup && (
          <a href={registryImage.config.application_setup} target="_blank" rel="noreferrer" className="flex items-center gap-1 text-xs text-primary hover:underline">
            <ExternalLink className="h-3 w-3" /> Application Setup Guide
          </a>
        )}

        <Separator />
        <div className="flex gap-2">
          <Button onClick={handleSaveAndLaunch} className="flex-1" disabled={createTemplate.isPending || createInstance.isPending}>
            {createInstance.isPending ? "Launching..." : "Save & Launch"}
          </Button>
          <Button variant="secondary" onClick={handleSaveTemplate} disabled={createTemplate.isPending}>
            Save as Template
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
