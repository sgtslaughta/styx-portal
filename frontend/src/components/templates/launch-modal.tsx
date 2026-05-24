import { useState } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { Separator } from "@/components/ui/separator";
import { EnvEditor } from "./env-editor";
import { useCreateTemplate } from "@/hooks/use-templates";
import { useCreateInstance } from "@/hooks/use-instances";
import { slugify } from "@/lib/utils";
import { toast } from "sonner";
import type { RegistryImage, ServiceTemplate } from "@/lib/types";

interface LaunchModalProps {
  open: boolean;
  onClose: () => void;
  registryImage?: RegistryImage | null;
  template?: ServiceTemplate | null;
}

export function LaunchModal({ open, onClose, registryImage, template }: LaunchModalProps) {
  const createTemplate = useCreateTemplate();
  const createInstance = useCreateInstance();

  const prefillName = registryImage?.name ?? template?.display_name ?? "";
  const prefillImage = registryImage ? `lscr.io/linuxserver/${registryImage.name}:latest` : template?.image ?? "";

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

  const prefillVolumes: { name: string; mount: string }[] = [];
  if (registryImage?.config?.volumes) {
    for (const v of registryImage.config.volumes) {
      prefillVolumes.push({ name: `{instance_id}${v.path.replace(/\//g, "-")}`, mount: v.path });
    }
  } else if (template?.volumes) {
    prefillVolumes.push(...template.volumes);
  }

  const [name, setName] = useState(prefillName);
  const [subdomain, setSubdomain] = useState(slugify(prefillName));
  const [image, setImage] = useState(prefillImage);
  const [memoryLimit, setMemoryLimit] = useState(template?.memory_limit ?? "4g");
  const [cpuLimit, setCpuLimit] = useState(template?.cpu_limit ?? "2.0");
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [envVars, setEnvVars] = useState(prefillEnv);
  const [gpuEnabled, setGpuEnabled] = useState(template?.gpu_enabled ?? false);
  const [gpuCount, setGpuCount] = useState(template?.gpu_count ?? 1);
  const [shmSize, setShmSize] = useState(template?.shm_size ?? "1g");
  const [volumes, setVolumes] = useState(prefillVolumes);
  const [idleTimeout, setIdleTimeout] = useState("30m");
  const [gracePeriod, setGracePeriod] = useState("5m");

  async function handleSaveAndLaunch() {
    try {
      const tmpl = await createTemplate.mutateAsync({
        name: slugify(name),
        display_name: name,
        image,
        description: registryImage?.description ?? template?.description ?? "",
        env_vars: envVars,
        gpu_enabled: gpuEnabled,
        gpu_count: gpuEnabled ? gpuCount : 0,
        memory_limit: memoryLimit,
        cpu_limit: cpuLimit,
        shm_size: shmSize,
        volumes,
        internal_port: 3001,
        category: registryImage?.category ?? template?.category ?? undefined,
        tags: [],
        session_config: { idle_timeout: idleTimeout, grace_period: gracePeriod, timeout_action: "stop", never_timeout: false, max_session_duration: null },
      });
      await createInstance.mutateAsync({ template_id: tmpl.id, name, subdomain });
      toast.success(`Instance "${name}" launched!`);
      onClose();
    } catch (e) {
      toast.error(`Launch failed: ${(e as Error).message}`);
    }
  }

  async function handleSaveTemplate() {
    try {
      await createTemplate.mutateAsync({
        name: slugify(name),
        display_name: name,
        image,
        description: registryImage?.description ?? template?.description ?? "",
        env_vars: envVars,
        gpu_enabled: gpuEnabled,
        gpu_count: gpuEnabled ? gpuCount : 0,
        memory_limit: memoryLimit,
        cpu_limit: cpuLimit,
        shm_size: shmSize,
        volumes,
        internal_port: 3001,
        category: registryImage?.category ?? template?.category ?? undefined,
        tags: [],
        session_config: { idle_timeout: idleTimeout, grace_period: gracePeriod, timeout_action: "stop", never_timeout: false, max_session_duration: null },
      });
      toast.success(`Template "${name}" saved!`);
      onClose();
    } catch (e) {
      toast.error(`Save failed: ${(e as Error).message}`);
    }
  }

  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="max-h-[85vh] max-w-xl overflow-y-auto">
        <DialogHeader>
          <DialogTitle>
            {registryImage ? `Import: ${registryImage.name}` : template ? `Launch: ${template.display_name}` : "Custom Template"}
          </DialogTitle>
        </DialogHeader>
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-3">
            <div><Label>Name</Label><Input value={name} onChange={(e) => { setName(e.target.value); setSubdomain(slugify(e.target.value)); }} /></div>
            <div><Label>Subdomain</Label><Input value={subdomain} onChange={(e) => setSubdomain(e.target.value)} className="font-mono text-sm" /></div>
          </div>
          <div><Label>Docker Image</Label><Input value={image} onChange={(e) => setImage(e.target.value)} className="font-mono text-sm" /></div>
          <div className="grid grid-cols-2 gap-3">
            <div><Label>Memory Limit</Label><Input value={memoryLimit} onChange={(e) => setMemoryLimit(e.target.value)} /></div>
            <div><Label>CPU Limit</Label><Input value={cpuLimit} onChange={(e) => setCpuLimit(e.target.value)} /></div>
          </div>

          <Separator />
          <button onClick={() => setShowAdvanced(!showAdvanced)} className="text-sm font-medium text-primary hover:underline">
            {showAdvanced ? "▾ Hide Advanced" : "▸ Show Advanced"}
          </button>

          {showAdvanced && (
            <div className="space-y-4">
              <div><Label className="mb-2 block">Environment Variables</Label><EnvEditor value={envVars} onChange={setEnvVars} descriptions={envDescriptions} /></div>
              <div>
                <Label className="mb-2 block">Volumes</Label>
                {volumes.map((vol, i) => (
                  <div key={i} className="mb-2 flex gap-2">
                    <Input value={vol.name} onChange={(e) => { const n = [...volumes]; n[i] = { ...vol, name: e.target.value }; setVolumes(n); }} placeholder="Volume name" className="flex-1 font-mono text-xs" />
                    <Input value={vol.mount} onChange={(e) => { const n = [...volumes]; n[i] = { ...vol, mount: e.target.value }; setVolumes(n); }} placeholder="/mount/path" className="flex-1 font-mono text-xs" />
                  </div>
                ))}
              </div>
              <div className="flex items-center gap-3">
                <Switch checked={gpuEnabled} onCheckedChange={setGpuEnabled} /><Label>GPU Passthrough</Label>
                {gpuEnabled && <Input type="number" value={gpuCount} onChange={(e) => setGpuCount(Number(e.target.value))} className="w-20" min={1} />}
              </div>
              <div><Label>SHM Size</Label><Input value={shmSize} onChange={(e) => setShmSize(e.target.value)} /></div>
              <div className="grid grid-cols-2 gap-3">
                <div><Label>Idle Timeout</Label><Input value={idleTimeout} onChange={(e) => setIdleTimeout(e.target.value)} /></div>
                <div><Label>Grace Period</Label><Input value={gracePeriod} onChange={(e) => setGracePeriod(e.target.value)} /></div>
              </div>
            </div>
          )}

          <Separator />
          <div className="flex gap-2">
            <Button onClick={handleSaveAndLaunch} className="flex-1">Save & Launch</Button>
            <Button variant="secondary" onClick={handleSaveTemplate}>Save as Template</Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
