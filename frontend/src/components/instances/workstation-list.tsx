import { api, type Workstation } from "@/api/client";
import { Thumbnail } from "@/components/common/thumbnail";
import { WorkstationIcon } from "@/components/system/workstation-icon";
import { WorkstationSpecs } from "@/components/system/workstation-specs";
import { cn } from "@/lib/utils";

/* ---------- LED status indicator ----------------------------------------- */

type Led = { color: string; pulse: boolean; label: string };

function ledFor(ws: Workstation): Led {
  if (ws.status === "revoked") return { color: "bg-rose-500", pulse: false, label: "Revoked" };
  if (ws.status !== "online")  return { color: "bg-muted-foreground", pulse: false, label: "Offline" };
  if (ws.last_error)           return { color: "bg-rose-400", pulse: true,  label: "Error" };
  if (ws.in_use)               return { color: "bg-amber-400", pulse: true, label: ws.in_use_self ? "Connected (you)" : `In use by ${ws.in_use_by ?? "someone"}` };
  return { color: "bg-emerald-400", pulse: true, label: "Online" };
}

function LedDot({ led }: { led: Led }) {
  return (
    <span className="relative flex h-2.5 w-2.5 shrink-0" title={led.label}>
      {led.pulse && (
        <span className={cn("absolute inline-flex h-full w-full animate-ping rounded-full opacity-50", led.color)} />
      )}
      <span className={cn("relative inline-flex h-2.5 w-2.5 rounded-full", led.color)} />
    </span>
  );
}

function fmtSeen(iso: string | null): string {
  if (!iso) return "never";
  const s = (Date.now() - new Date(iso).getTime()) / 1000;
  if (s < 90) return "just now";
  if (s < 3600) return `${Math.round(s / 60)}m ago`;
  if (s < 86400) return `${Math.round(s / 3600)}h ago`;
  return new Date(iso).toLocaleDateString();
}

/** Detail-pane preview for a selected workstation: live thumbnail + status and specs. */
export function WorkstationPreview({ ws }: { ws: Workstation }) {
  const led = ledFor(ws);
  return (
    <div className="space-y-3 p-4" data-testid="ws-preview">
      <div className="flex items-center gap-2">
        <LedDot led={led} />
        <WorkstationIcon ws={ws} />
        <h3 className="min-w-0 flex-1 truncate text-base font-semibold">{ws.name}</h3>
      </div>
      <Thumbnail src={api.workstationThumbUrl(ws.id)} icon={null} isLive={ws.status === "online"} />
      <p className="text-xs text-muted-foreground">{led.label} · seen {fmtSeen(ws.last_heartbeat)}</p>
      <WorkstationSpecs ws={ws} />
    </div>
  );
}
