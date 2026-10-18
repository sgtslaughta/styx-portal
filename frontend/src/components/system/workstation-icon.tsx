import type { Workstation } from "@/api/client";
import { cn } from "@/lib/utils";

/** Decorative icon; the workstation name is always rendered next to it. */
export function WorkstationIcon({ ws, className }: { ws: Workstation; className?: string }) {
  return (
    <img
      src={`/api/workstations/${ws.id}/icon?v=${ws.icon_etag}`}
      alt=""
      className={cn("h-6 w-6 shrink-0 rounded-md", className)}
    />
  );
}
