import type { Workstation } from "@/api/client";
import { GlassButton } from "@/components/ui/glass-button";
import { WorkstationIcon } from "@/components/system/workstation-icon";
import { RowMenu } from "./row-menu";

export function wsStatus(ws: Workstation): string {
  if (ws.status !== "online") return "Offline";
  if (ws.in_use_self) return "Connected (you)";
  if (ws.in_use) return `In use by ${ws.in_use_by ?? "someone"}`;
  return "Online";
}

interface Props {
  workstations: Workstation[];
  onConnect: (ws: Workstation) => void;
  onDetails: (ws: Workstation) => void;
}

export function DesktopTiles({ workstations, onConnect, onDetails }: Props) {
  if (workstations.length === 0) return <p className="text-sm text-muted-foreground">No desktops shared with you yet.</p>;
  return (
    <ul className="grid grid-cols-[repeat(auto-fill,minmax(220px,1fr))] gap-2.5">
      {workstations.map((ws) => {
        const online = ws.status === "online";
        return (
          <li key={ws.id} className="glass-reveal group relative flex items-center gap-3 rounded-xl border border-border bg-card p-3 hover:bg-secondary/60"
           >
            <span className="grid size-10 shrink-0 place-items-center rounded-[10px] bg-secondary text-primary">
              <WorkstationIcon ws={ws} className="size-6" />
            </span>
            <div className="min-w-0 flex-1">
              <strong className="block truncate text-sm font-semibold">{ws.name}</strong>
              <small className="block truncate text-[12.5px] text-muted-foreground transition-opacity group-hover:opacity-35 [@media(hover:none)]:group-hover:opacity-100">{wsStatus(ws)}</small>
            </div>
            {online && (
              <span className="absolute right-12 top-1/2 -translate-y-1/2">
                <GlassButton tone="teal" onClick={() => onConnect(ws)} aria-label={`${ws.in_use_self ? "Resume" : "Connect"} ${ws.name}`}>
                  {ws.in_use_self ? "Resume" : "Connect"}
                </GlassButton>
              </span>
            )}
            <RowMenu name={ws.name} onDetails={() => onDetails(ws)} />
          </li>
        );
      })}
    </ul>
  );
}
