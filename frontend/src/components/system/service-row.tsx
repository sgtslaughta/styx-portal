import { Pencil, Trash2 } from "lucide-react";
import type { MountJob, ProxiedService } from "@/api/client";
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

const RISKY = "border-warning/50 bg-warning/15 text-foreground";
const DANGER = "border-destructive/40 bg-destructive/10 text-foreground";

/** One badge per decision: mount, auth, then TLS/fallback only when they deviate. */
function badges(s: ProxiedService): { key: string; label: string; cls?: string; title: string }[] {
  const out: { key: string; label: string; cls?: string; title: string }[] = [
    s.mount_mode === "cookie-root"
      ? { key: "mount", label: "Cookie root", cls: RISKY, title: "Mount mode: cookie root (takes over the browser)" }
      : { key: "mount", label: "Path", title: "Mount mode: path" },
  ];
  if (s.auth_mode === "sso") out.push({ key: "auth", label: "SSO", title: "Styx login required" });
  if (s.auth_mode === "sso-with-bypass") {
    const n = s.bypass_rules.length;
    out.push({ key: "auth", label: `SSO, ${n} ${n === 1 ? "bypass" : "bypasses"}`, cls: RISKY, title: "Some paths skip the Styx login" });
  }
  if (s.auth_mode === "app-native") out.push({ key: "auth", label: "No Styx login", cls: DANGER, title: "The app enforces its own login" });
  if (!s.verify_tls) out.push({ key: "tls", label: "TLS unverified", cls: RISKY, title: "Upstream certificate is not verified" });
  if (s.upstream_fallback) out.push({ key: "fb", label: "Host fallback", title: "Container unreachable by name; using the host address" });
  return out;
}

const MOUNT_CHIP = {
  done: { label: "Base path set", cls: "border-obol/60 text-obol-foreground" },
  rolled_back: { label: "Rolled back", cls: "border-destructive/40 text-destructive" },
  failed: { label: "Needs attention", cls: "border-destructive/40 text-destructive" },
} as const;

export function ServiceRow({ s, busy, lastMount, onToggle, onEdit, onDelete }: {
  s: ProxiedService; busy: boolean; lastMount?: MountJob["state"]; onToggle: (v: boolean) => void; onEdit: () => void; onDelete: () => void;
}) {
  const label = s.health_status === "unknown" ? "Not checked yet" : s.health_status === "healthy" ? "Healthy" : "Unhealthy";
  const target = s.kind === "url" ? s.upstream_url : `${s.container}:${s.container_port}`;
  return (
    <li className="flex items-start gap-3 rounded-lg border border-border bg-muted/30 p-3 sm:items-center">
      <Tooltip>
        <TooltipTrigger asChild>
          <span tabIndex={0} role="img" aria-label={`Health: ${s.health_status}`}
            className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full focus-visible:outline-2 focus-visible:outline-ring sm:mt-0">
            <span className={cn("h-2.5 w-2.5 rounded-full", DOT[s.health_status])} />
          </span>
        </TooltipTrigger>
        <TooltipContent>{label}, {ago(s.health_checked_at)}</TooltipContent>
      </Tooltip>
      <div className={cn("min-w-0 flex-1", !s.enabled && "opacity-60")}>
        <div className="flex flex-wrap items-baseline gap-x-2">
          <span className="truncate font-medium">{s.icon ? `${s.icon} ` : ""}{s.name}</span>
          <code className="text-xs text-muted-foreground">/{s.slug}</code>
          {!s.enabled && <span className="text-xs text-muted-foreground">Disabled</span>}
        </div>
        <p className="truncate font-mono text-xs text-muted-foreground" title={target ?? undefined}>{target}</p>
        <div className="mt-2 flex flex-wrap gap-1.5">
          {badges(s).map((b) => (
            <Badge key={b.key} variant={b.cls ? "outline" : "secondary"} className={b.cls} title={b.title}>{b.label}</Badge>
          ))}
          {lastMount && lastMount in MOUNT_CHIP && (
            <Badge variant="outline" className={MOUNT_CHIP[lastMount as keyof typeof MOUNT_CHIP].cls}>
              {MOUNT_CHIP[lastMount as keyof typeof MOUNT_CHIP].label}
            </Badge>
          )}
        </div>
      </div>
      <div className="flex shrink-0 flex-col-reverse items-end gap-1 sm:flex-row sm:items-center">
        <Switch size="sm" checked={s.enabled} disabled={busy} aria-label={`Enable ${s.name}`} title={s.enabled ? "Enabled" : "Disabled"}
          className="sm:mr-1" onCheckedChange={onToggle} />
        <div className="flex">
          <Button variant="ghost" size="icon-sm" aria-label={`Edit ${s.name}`} title="Edit" onClick={onEdit}><Pencil className="h-4 w-4" /></Button>
          <Button variant="ghost" size="icon-sm" aria-label={`Delete ${s.name}`} title="Delete"
            className="text-muted-foreground hover:bg-destructive/10 hover:text-destructive" onClick={onDelete}>
            <Trash2 className="h-4 w-4" />
          </Button>
        </div>
      </div>
    </li>
  );
}
