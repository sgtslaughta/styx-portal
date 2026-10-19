import { useState } from "react";
import type { Workstation } from "@/api/client";
import { cn } from "@/lib/utils";

/** Decorative icon (initial tile if the image fails); the workstation name is always rendered next to it. */
export function WorkstationIcon({ ws, className }: { ws: Workstation; className?: string }) {
  const key = `${ws.id}:${ws.icon_etag}`;
  const [failed, setFailed] = useState<string | null>(null);
  if (failed === key) {
    return (
      <span aria-hidden className={cn("flex h-6 w-6 shrink-0 items-center justify-center rounded-md bg-muted font-semibold text-muted-foreground", className)}>
        {ws.name.charAt(0).toUpperCase()}
      </span>
    );
  }
  return (
    <img
      src={`/api/workstations/${ws.id}/icon?v=${ws.icon_etag}`}
      alt=""
      onError={() => setFailed(key)}
      className={cn("h-6 w-6 shrink-0 rounded-md", className)}
    />
  );
}
