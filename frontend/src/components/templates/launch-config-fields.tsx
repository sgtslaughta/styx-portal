import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { Separator } from "@/components/ui/separator";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { EnvEditor } from "./env-editor";
import { GpuIndicator } from "./launch-gpu-indicator";
import { SelkiesSettings } from "./launch-selkies-settings";
import { Plus, Trash2, Shield, HardDrive, Network, Settings2, Info, Monitor } from "lucide-react";
import type { LaunchConfig } from "@/hooks/use-launch-config";

interface LaunchConfigFieldsProps {
  cfg: LaunchConfig;
  gpuInfo: { available: boolean; type: string | null; devices: string[] } | undefined;
}

export function LaunchConfigFields({ cfg, gpuInfo }: LaunchConfigFieldsProps) {
  return (
    <>
      {/* Core fields */}
      <div className="space-y-3">
        <div className="grid grid-cols-2 gap-3">
          <div>
            <Label>Name</Label>
            <Input
              value={cfg.name}
              onChange={(e) => {
                cfg.setName(e.target.value);
                cfg.setSubdomain(e.target.value.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, ""));
              }}
            />
          </div>
          <div>
            <Label>Subdomain</Label>
            <Input value={cfg.subdomain} onChange={(e) => cfg.setSubdomain(e.target.value)} className="font-mono text-sm" />
          </div>
        </div>
        <div className="grid grid-cols-[1fr_200px] gap-3">
          <div className="min-w-0">
            <Label>Docker Image</Label>
            <Input value={cfg.image} onChange={(e) => cfg.setImage(e.target.value)} className="font-mono text-sm" />
          </div>
          <div className="min-w-0">
            <Label>Icon URL</Label>
            <Input value={cfg.icon} onChange={(e) => cfg.setIcon(e.target.value)} placeholder="https://..." className="text-sm" />
          </div>
        </div>
      </div>

      <Separator />

      {/* GPU Indicator */}
      <GpuIndicator gpuInfo={gpuInfo} gpuEnabled={cfg.gpuEnabled} setGpuEnabled={cfg.setGpuEnabled} gpuDevices={cfg.gpuDevices} setGpuDevices={cfg.setGpuDevices} />

      <Separator />

      {/* Tabbed config sections */}
      <Tabs defaultValue="resources" className="w-full min-w-0 overflow-hidden">
        <TabsList className="w-full grid grid-cols-6 gap-1 p-1">
          <TabsTrigger value="resources" className="text-xs gap-1.5 px-3">
            <Settings2 className="h-3.5 w-3.5" />
            Resources
          </TabsTrigger>
          <TabsTrigger value="env" className="text-xs gap-1.5 px-3">
            <Info className="h-3.5 w-3.5" />
            Env
          </TabsTrigger>
          <TabsTrigger value="volumes" className="text-xs gap-1.5 px-3">
            <HardDrive className="h-3.5 w-3.5" />
            Volumes
          </TabsTrigger>
          <TabsTrigger value="network" className="text-xs gap-1.5 px-3">
            <Network className="h-3.5 w-3.5" />
            Ports
          </TabsTrigger>
          <TabsTrigger value="security" className="text-xs gap-1.5 px-3">
            <Shield className="h-3.5 w-3.5" />
            Security
          </TabsTrigger>
          <TabsTrigger value="selkies" className="text-xs gap-1.5 px-3">
            <Monitor className="h-3.5 w-3.5" />
            Selkies
          </TabsTrigger>
        </TabsList>

        <TabsContent value="resources" className="space-y-4 mt-4">
          <div className="grid grid-cols-3 gap-3">
            <div>
              <Label>Memory</Label>
              <Input value={cfg.memoryLimit} onChange={(e) => cfg.setMemoryLimit(e.target.value)} placeholder="4g" />
            </div>
            <div>
              <Label>CPU</Label>
              <Input value={cfg.cpuLimit} onChange={(e) => cfg.setCpuLimit(e.target.value)} placeholder="2.0" />
            </div>
            <div>
              <Label>SHM Size</Label>
              <Input value={cfg.shmSize} onChange={(e) => cfg.setShmSize(e.target.value)} placeholder="1g" />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label>Idle Timeout</Label>
              <Input value={cfg.idleTimeout} onChange={(e) => cfg.setIdleTimeout(e.target.value)} />
            </div>
            <div>
              <Label>Grace Period</Label>
              <Input value={cfg.gracePeriod} onChange={(e) => cfg.setGracePeriod(e.target.value)} />
            </div>
          </div>
          {/* Custom Docker Options */}
          {cfg.customOpts.length > 0 && (
            <div>
              <Label className="mb-2 block text-xs text-muted-foreground">Custom Docker Options</Label>
              {cfg.customOpts.map((opt, i) => (
                <div key={i} className="mb-2 flex items-center gap-2 min-w-0">
                  <Input
                    value={opt.name}
                    onChange={(e) => {
                      const n = [...cfg.customOpts];
                      n[i] = { ...opt, name: e.target.value };
                      cfg.setCustomOpts(n);
                    }}
                    placeholder="option"
                    className="w-32 shrink-0 font-mono text-xs"
                  />
                  <Input
                    value={opt.value}
                    onChange={(e) => {
                      const n = [...cfg.customOpts];
                      n[i] = { ...opt, value: e.target.value };
                      cfg.setCustomOpts(n);
                    }}
                    placeholder="value"
                    className="flex-1 min-w-0 font-mono text-xs"
                  />
                  {opt.desc && <span className="text-[10px] text-muted-foreground max-w-40 truncate shrink-0" title={opt.desc}>{opt.desc}</span>}
                  <Button variant="ghost" size="icon" className="h-7 w-7 shrink-0" onClick={() => cfg.setCustomOpts(cfg.customOpts.filter((_, j) => j !== i))}>
                    <Trash2 className="h-3 w-3" />
                  </Button>
                </div>
              ))}
            </div>
          )}
          <Button variant="outline" size="sm" onClick={() => cfg.setCustomOpts([...cfg.customOpts, { name: "", value: "", desc: "" }])}>
            <Plus className="mr-1 h-3 w-3" /> Add Docker Option
          </Button>
        </TabsContent>

        <TabsContent value="env" className="mt-4">
          <EnvEditor value={cfg.envVars} onChange={cfg.setEnvVars} descriptions={cfg.envDescriptions} />
        </TabsContent>

        <TabsContent value="volumes" className="space-y-3 mt-4">
          {cfg.volumes.map((vol, i) => (
            <div key={i} className="flex items-start gap-2 min-w-0">
              <div className="flex-1 min-w-0">
                <Input
                  value={vol.name}
                  onChange={(e) => {
                    const n = [...cfg.volumes];
                    n[i] = { ...vol, name: e.target.value };
                    cfg.setVolumes(n);
                  }}
                  placeholder="volume-name"
                  className="font-mono text-xs"
                />
                {vol.desc && <p className="mt-0.5 text-[10px] text-muted-foreground truncate">{vol.desc}</p>}
              </div>
              <Input
                value={vol.mount}
                onChange={(e) => {
                  const n = [...cfg.volumes];
                  n[i] = { ...vol, mount: e.target.value };
                  cfg.setVolumes(n);
                }}
                placeholder="/mount/path"
                className="flex-1 min-w-0 font-mono text-xs"
              />
              <Button variant="ghost" size="icon" className="h-9 w-9 shrink-0" onClick={() => cfg.setVolumes(cfg.volumes.filter((_, j) => j !== i))}>
                <Trash2 className="h-3 w-3" />
              </Button>
            </div>
          ))}
          <Button variant="outline" size="sm" onClick={() => cfg.setVolumes([...cfg.volumes, { name: "", mount: "" }])}>
            <Plus className="mr-1 h-3 w-3" /> Add Volume
          </Button>
        </TabsContent>

        <TabsContent value="network" className="space-y-3 mt-4">
          {/* Web UI port the reverse proxy connects to. Auto-detected from the
              registry image (HTTPS preferred); override here if needed. */}
          <div className="rounded-md border border-border p-3">
            <Label className="text-xs text-muted-foreground">Web UI port (reverse-proxy target)</Label>
            <div className="mt-1.5 flex items-center gap-2">
              <Input
                type="number"
                value={cfg.internalPort}
                onChange={(e) => cfg.setInternalPort(Number(e.target.value))}
                className="w-28 font-mono text-sm"
                placeholder="3001"
              />
              <select
                value={cfg.internalProtocol}
                onChange={(e) => cfg.setInternalProtocol(e.target.value)}
                className="h-9 rounded-md border border-input bg-background px-2 text-sm outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50"
              >
                <option value="https">https</option>
                <option value="http">http</option>
              </select>
            </div>
            <p className="mt-1.5 text-[10px] text-muted-foreground">
              Auto-detected from the image. LinuxServer Selkies/KasmVNC images serve the GUI on 3001 (HTTPS) / 3000 (HTTP). Change only if the image serves elsewhere.
            </p>
          </div>
          <p className="text-[10px] text-muted-foreground mb-2">Additional ports below are reference-only (not published).</p>
          {cfg.ports.map((port, i) => (
            <div key={i} className="flex items-start gap-2">
              <div className="flex-1">
                <div className="flex gap-2">
                  <Input
                    value={port.internal}
                    onChange={(e) => {
                      const n = [...cfg.ports];
                      n[i] = { ...port, internal: e.target.value };
                      cfg.setPorts(n);
                    }}
                    placeholder="container"
                    className="w-20 font-mono text-xs"
                  />
                  <span className="self-center text-xs text-muted-foreground">→</span>
                  <Input
                    value={port.external}
                    onChange={(e) => {
                      const n = [...cfg.ports];
                      n[i] = { ...port, external: e.target.value };
                      cfg.setPorts(n);
                    }}
                    placeholder="host"
                    className="w-20 font-mono text-xs"
                  />
                </div>
                {port.desc && <p className="mt-0.5 text-[10px] text-muted-foreground">{port.desc}</p>}
              </div>
              <Button variant="ghost" size="icon" className="h-9 w-9" onClick={() => cfg.setPorts(cfg.ports.filter((_, j) => j !== i))}>
                <Trash2 className="h-3 w-3" />
              </Button>
            </div>
          ))}
          <Button variant="outline" size="sm" onClick={() => cfg.setPorts([...cfg.ports, { internal: "", external: "" }])}>
            <Plus className="mr-1 h-3 w-3" /> Add Port
          </Button>
        </TabsContent>

        <TabsContent value="security" className="space-y-4 mt-4">
          {cfg.securityOpts.length > 0 && (
            <div className="space-y-2">
              {cfg.securityOpts.map((opt, i) => (
                <div key={i} className="flex items-center gap-3 rounded-md border border-border p-2">
                  <Switch
                    checked={opt.enabled}
                    onCheckedChange={(v) => {
                      const n = [...cfg.securityOpts];
                      n[i] = { ...opt, enabled: v };
                      cfg.setSecurityOpts(n);
                    }}
                  />
                  <div className="flex-1">
                    <code className="text-xs">{opt.value}</code>
                    {opt.desc && <p className="text-[10px] text-muted-foreground">{opt.desc}</p>}
                  </div>
                  <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => cfg.setSecurityOpts(cfg.securityOpts.filter((_, j) => j !== i))}>
                    <Trash2 className="h-3 w-3" />
                  </Button>
                </div>
              ))}
            </div>
          )}
          <Button variant="outline" size="sm" onClick={() => cfg.setSecurityOpts([...cfg.securityOpts, { value: "", desc: "", enabled: true }])}>
            <Plus className="mr-1 h-3 w-3" /> Add Security Option
          </Button>
          {cfg.securityOpts.length === 0 && (
            <p className="text-xs text-muted-foreground">No security options configured. Default: seccomp=unconfined, apparmor=unconfined applied automatically.</p>
          )}
        </TabsContent>

        <TabsContent value="selkies" className="mt-4">
          <SelkiesSettings envVars={cfg.envVars} onChange={cfg.setEnvVars} />
        </TabsContent>
      </Tabs>
    </>
  );
}
