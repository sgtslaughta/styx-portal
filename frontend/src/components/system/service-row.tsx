import { Pencil, Trash2 } from "lucide-react";
import type { ProxiedService } from "@/api/client";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";

const DOT = { healthy: "bg-success", unhealthy: "bg-destructive", unknown: "bg-muted-foreground/50" } as const;

function ago(iso: string | null): string {
  if (!iso) return "never checked";
  const s = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 1000));
  if (Number.isNaN(s)) return "never checked";
  if (s < 60) return "checked just now";
  if (s < 3600) return `checked ${Math.floor(s / 60)} min ago`;
  if (s < 86400) return `checked ${Math.floor(s / 3600)} h ago`;
  return `checked ${Math.floor(s / 86400)} d ago`;
}

export function ServiceRow({ s, busy, onToggle, onEdit, onDelete }: {
  s: ProxiedService; busy: boolean; onToggle: (v: boolean) => void; onEdit: () => void; onDelete: () => void;
}) {
  const label = s.health_status === "unknown" ? "Not checked yet" : s.health_status === "healthy" ? "Healthy" : "Unhealthy";
  const target = s.kind === "url" ? s.upstream_url : `${s.container}:${s.container_port}`;
  return (
    <li className={cn("flex flex-wrap items-center gap-3 rounded-lg border border-border bg-surface p-3", !s.enabled && "opacity-60")}>
      <Tooltip>
        <TooltipTrigger asChild>
          <span tabIndex={0} role="img" aria-label={`Health: ${s.health_status}`} className="flex h-5 w-5 items-center justify-center">
            <span className={cn("h-2.5 w-2.5 rounded-full", DOT[s.health_status])} />
          </span>
        </TooltipTrigger>
        <TooltipContent>{label}, {ago(s.health_checked_at)}</TooltipContent>
      </Tooltip>
      <div className="min-w-0 flex-1 basis-56">
        <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
          <span className="font-medium">{s.icon ? `${s.icon} ` : ""}{s.name}</span>
          <code className="rounded bg-muted px-1.5 py-0.5 text-xs text-muted-foreground">/{s.slug}</code>
        </div>
        <p className="truncate text-xs text-muted-foreground" title={target ?? undefined}>{target}</p>
        <div className="mt-1.5 flex flex-wrap gap-1.5">
          <Badge variant={s.mount_mode === "cookie-root" ? "destructive" : "secondary"}>{s.mount_mode === "path" ? "path" : "cookie-root"}</Badge>
          {s.auth_mode === "sso" && <Badge variant="secondary">SSO</Badge>}
          {s.auth_mode === "sso-with-bypass" && (
            <Badge variant="outline" className="border-warning/60 text-warning">SSO + bypass ({s.bypass_rules.length})</Badge>
          )}
          {s.auth_mode === "app-native" && <Badge variant="destructive">app-native auth</Badge>}
          {!s.verify_tls && <Badge variant="outline" className="border-warning/60 text-warning">TLS not verified</Badge>}
          {s.upstream_fallback && <Badge variant="outline">host fallback</Badge>}
        </div>
      </div>
      <div className="flex items-center gap-2">
        <Switch size="sm" checked={s.enabled} disabled={busy} aria-label={`Enable ${s.name}`} onCheckedChange={onToggle} />
        <Button variant="ghost" size="icon-sm" aria-label={`Edit ${s.name}`} title="Edit" onClick={onEdit}><Pencil className="h-4 w-4" /></Button>
        <Button variant="destructive" size="icon-sm" aria-label={`Delete ${s.name}`} title="Delete" onClick={onDelete}><Trash2 className="h-4 w-4" /></Button>
      </div>
    </li>
  );
}
