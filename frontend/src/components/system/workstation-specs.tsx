import {
  Cpu, MemoryStick, HardDrive, CircuitBoard, Cog,
  Monitor, Network, Tag, Clock, User, Server, type LucideIcon,
} from "lucide-react";
import {
  Tooltip, TooltipTrigger, TooltipContent, TooltipProvider,
} from "@/components/ui/tooltip";
import type { Workstation } from "@/api/client";
import { cn } from "@/lib/utils";

/* Compact spec row: a colored glyph per known field; the value lives in the
   hover tooltip. Shared by the admin panel and the user-facing list so both
   read identically. OS is shown separately (brand badge), not here. */

type Spec = { icon: LucideIcon; color: string; label: string; value: string };

function fmtSeen(iso: string | null): string {
  if (!iso) return "never";
  const s = (Date.now() - new Date(iso).getTime()) / 1000;
  if (s < 90) return "just now";
  if (s < 3600) return `${Math.round(s / 60)}m ago`;
  if (s < 86400) return `${Math.round(s / 3600)}h ago`;
  return new Date(iso).toLocaleString();
}

function specsFor(ws: Workstation): Spec[] {
  const os = ws.os_info as Record<string, string | number | undefined>;
  const gpu = ws.gpu_info as Record<string, string | undefined>;
  const out: Spec[] = [];

  if (os.pretty_name || os.distro)
    out.push({ icon: Server, color: "text-indigo-400", label: "OS",
      value: String(os.pretty_name || os.distro) });
  if (os.cpu_model != null)
    out.push({ icon: Cpu, color: "text-sky-400", label: "CPU",
      value: `${os.cpu_model}${os.cpu_cores ? ` · ${os.cpu_cores}c` : ""}` });
  if (os.memory_mb != null)
    out.push({ icon: MemoryStick, color: "text-violet-400", label: "RAM",
      value: `${Math.round(Number(os.memory_mb) / 1024)} GB` });
  if (os.disk_total_gb != null)
    out.push({ icon: HardDrive, color: "text-amber-400", label: "Disk",
      value: `${os.disk_free_gb} / ${os.disk_total_gb} GB free` });
  if (gpu.model || gpu.vendor)
    out.push({ icon: CircuitBoard, color: "text-emerald-400", label: "GPU",
      value: String(gpu.model || gpu.vendor) });
  if (os.kernel != null)
    out.push({ icon: Cog, color: "text-slate-400", label: "Kernel",
      value: String(os.kernel) });

  out.push({ icon: Monitor, color: "text-cyan-400", label: "Session",
    value: `${ws.display_server}${os.mode ? ` (${os.mode})` : ""}` });
  if (ws.lan_ip)
    out.push({ icon: Network, color: "text-blue-400", label: "Address",
      value: `${ws.lan_ip}:${ws.port}` });
  if (ws.agent_version)
    out.push({ icon: Tag,
      color: ws.agent_outdated ? "text-amber-400" : "text-fuchsia-400",
      label: "Agent",
      value: `v${ws.agent_version}${ws.agent_outdated ? " · outdated" : ""}` });
  out.push({ icon: Clock, color: "text-zinc-400", label: "Last seen",
    value: fmtSeen(ws.last_heartbeat) });
  if (ws.in_use)
    out.push({ icon: User, color: "text-amber-400", label: "In use by",
      value: ws.in_use_self ? "you" : (ws.in_use_by ?? "someone") });

  return out;
}

export function WorkstationSpecs({ ws, className }: { ws: Workstation; className?: string }) {
  const specs = specsFor(ws);
  return (
    <TooltipProvider>
      <div className={cn("flex flex-wrap items-center gap-x-3 gap-y-2", className)}>
        {specs.map((s) => {
          const Icon = s.icon;
          return (
            <Tooltip key={s.label}>
              <TooltipTrigger asChild>
                <span className="inline-flex items-center gap-1.5 cursor-default" tabIndex={0}
                      aria-label={`${s.label}: ${s.value}`}>
                  <Icon className={cn("h-4 w-4 shrink-0", s.color)} />
                  <span className="text-xs text-muted-foreground">{s.value}</span>
                </span>
              </TooltipTrigger>
              <TooltipContent>{s.label}</TooltipContent>
            </Tooltip>
          );
        })}
      </div>
    </TooltipProvider>
  );
}
