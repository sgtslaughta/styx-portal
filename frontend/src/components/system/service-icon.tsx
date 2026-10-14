import { cn } from "@/lib/utils";

/** Decorative icon (the service name is always rendered next to it). Bytes come from the server. */
export function ServiceIcon({ s, className }: { s: { id: string; icon_etag: string }; className?: string }) {
  return (
    <img
      src={`/api/services/${s.id}/icon?v=${s.icon_etag}`}
      alt=""
      className={cn("size-7 shrink-0 rounded-md", className)}
    />
  );
}
