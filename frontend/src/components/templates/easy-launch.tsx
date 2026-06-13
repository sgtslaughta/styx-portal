import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { Cpu, HardDrive, Globe, ShieldCheck } from "lucide-react";
import type { LaunchConfig } from "@/hooks/use-launch-config";

interface EasyLaunchProps {
  cfg: LaunchConfig;
  domain: string;
  onLaunch: () => void;
  onAdvanced: () => void;
  launching: boolean;
}

export function EasyLaunch({ cfg, domain, onLaunch, onAdvanced, launching }: EasyLaunchProps) {
  return (
    <div className="grid grid-cols-1 gap-4 md:grid-cols-[44%_56%]">
      {/* What you get summary */}
      <div className="space-y-2 rounded-lg bg-muted/40 p-4">
        <div className="text-xs uppercase tracking-wide text-muted-foreground">What you get</div>
        <ul className="space-y-1.5 text-sm">
          <li className="flex items-center gap-2">
            <Cpu className="h-4 w-4 flex-shrink-0" />
            <span>
              {cfg.gpuEnabled ? "GPU · " : ""}
              {cfg.memoryLimit} RAM · {cfg.cpuLimit} vCPU
            </span>
          </li>
          <li className="flex items-center gap-2">
            <HardDrive className="h-4 w-4 flex-shrink-0" />
            <span>Persistent storage</span>
          </li>
          <li className="flex items-center gap-2">
            <Globe className="h-4 w-4 flex-shrink-0" />
            <span className="font-mono text-xs">
              {cfg.subdomain || "instance"}
              {domain && `.${domain}`}
            </span>
          </li>
          <li className="flex items-center gap-2">
            <ShieldCheck className="h-4 w-4 flex-shrink-0" />
            <span>Auth required</span>
          </li>
        </ul>
      </div>

      {/* Minimal form */}
      <div className="space-y-3">
        <div>
          <Label htmlFor="easy-name">Name</Label>
          <Input
            id="easy-name"
            value={cfg.name}
            onChange={(e) => cfg.setName(e.target.value)}
            placeholder="e.g., My Instance"
          />
        </div>
        <div>
          <Label htmlFor="easy-address">Address</Label>
          <Input
            id="easy-address"
            value={cfg.subdomain}
            onChange={(e) => cfg.setSubdomain(e.target.value)}
            placeholder="my-instance"
            className="font-mono text-sm"
          />
        </div>
        <Button
          onClick={onLaunch}
          disabled={launching}
          className="w-full"
        >
          {launching ? "Launching..." : "Launch"}
        </Button>
        <button
          type="button"
          className="w-full text-xs text-muted-foreground hover:text-foreground transition-colors"
          onClick={onAdvanced}
        >
          Switch to Advanced →
        </button>
      </div>
    </div>
  );
}
