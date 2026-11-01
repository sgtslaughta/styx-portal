import { motion, useReducedMotion } from "framer-motion";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/api/client";
import { useInstances } from "@/hooks/use-instances";
import { useSystemMetrics, useResourceHistory } from "@/hooks/use-system";
import { AlertTriangle } from "lucide-react";
import { formatDuration } from "@/lib/utils";
import { OverviewCard, Figure, Sparkline, type Level } from "./overview-cards";

function EventRow({ event }: { event: { type: string; instance: string; time: string; details?: string } }) {
  const typeColors: Record<string, string> = {
    started: "text-emerald-400",
    stopped: "text-muted-foreground",
    error: "text-destructive",
    restarted: "text-primary",
    paused: "text-warning-foreground",
    created: "text-purple-400",
  };

  return (
    <div className="flex items-center gap-3 py-2 px-3 rounded-md hover:bg-muted/30 transition-colors group">
      <div className={`h-1.5 w-1.5 rounded-full ${event.type === "paused" ? "bg-warning" : typeColors[event.type]?.replace("text-", "bg-") ?? "bg-muted-foreground"}`} />
      <span className="text-xs text-foreground flex-1 truncate">{event.instance}</span>
      <span className={`text-[11px] font-medium ${typeColors[event.type] ?? "text-muted-foreground"}`}>
        {event.type}
      </span>
      <span className="text-[10px] text-muted-foreground/60 tabular-nums w-14 text-right">
        {event.time}
      </span>
    </div>
  );
}

const HEALTH_LABELS: Record<string, string> = {
  docker: "Docker engine", kubernetes: "Kubernetes API", database: "Database",
  traefik_routes: "Traefik routing", disk: "Disk space", gpu: "GPU",
};

export function MetricsOverview() {
  const { data: instances } = useInstances();
  const { data: metrics } = useSystemMetrics();
  const { data: history } = useResourceHistory("1h");
  const { data: diag } = useQuery({
    queryKey: ["diagnostics"], queryFn: api.getDiagnostics, refetchInterval: 30000,
  });
  const reduce = useReducedMotion();

  const c = { running: 0, idle: 0, paused: 0, stopped: 0, error: 0, total: 0 };
  instances?.forEach((i) => {
    c.total++;
    if (i.status === "running") c.running++;
    else if (i.status === "idle") c.idle++;
    else if (i.status === "paused") c.paused++;
    else if (i.status === "error") c.error++;
    else c.stopped++;
  });

  const events = metrics?.recent_events ?? [];
  const errorEvents = events.filter((e) => e.type === "error").length;
  const host = metrics?.host ?? {};
  const cpu = metrics?.aggregate_cpu ?? 0;
  const ram = metrics?.aggregate_ram_mb ?? 0;
  const diskUsed = metrics?.disk_used_gb ?? 0;
  const diskTotal = metrics?.disk_total_gb ?? 0;
  const diskPct = diskTotal > 0 ? diskUsed / diskTotal : 0;

  const checks = diag?.checks ?? [];
  const failing = checks.filter((k) => !k.ok);
  const healthLevel: Level = failing.length > 0 ? "error" : "ok";
  const sessionLevel: Level = c.error > 0 ? "error" : c.paused > 0 ? "warn" : "ok";
  const resLevel: Level = diskPct > 0.9 || cpu > 90 ? "error" : diskPct > 0.8 || cpu > 75 ? "warn" : "ok";
  const logLevel: Level = errorEvents > 0 ? "warn" : "ok";

  return (
    <div className="space-y-6">
      {c.error > 0 && (
        <motion.div
          initial={reduce ? false : { opacity: 0, height: 0 }}
          animate={reduce ? {} : { opacity: 1, height: "auto" }}
          className="flex items-center gap-3 rounded-lg border border-destructive/30 bg-destructive/5 px-4 py-3"
        >
          <AlertTriangle className="h-4 w-4 text-destructive" />
          <span className="text-sm text-destructive/80">
            {c.error} instance{c.error > 1 ? "s" : ""} in error state
          </span>
        </motion.div>
      )}

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <OverviewCard section="health" level={healthLevel}>
          <Figure label="Checks" value={`${checks.length - failing.length} ok / 0 warn / ${failing.length} fail`} />
          <Figure label="Status" value={failing.length ? `${failing.length} failing` : "All passing"} />
          {failing.slice(0, 3).map((k) => (
            <div key={k.key} className="text-destructive">{HEALTH_LABELS[k.key] ?? k.key}</div>
          ))}
          <Figure label="Last checked" value={diag?.checked_at ? new Date(diag.checked_at).toLocaleTimeString() : "—"} />
        </OverviewCard>

        <OverviewCard section="sessions" level={sessionLevel}>
          <Figure label="Running" value={c.running} />
          <Figure label="Idle" value={c.idle} />
          <Figure label="Paused" value={c.paused} />
          <Figure label="Stopped" value={c.stopped} />
          <Figure label="Error" value={c.error} />
        </OverviewCard>

        <OverviewCard section="resources" level={resLevel}>
          <Figure label="CPU" value={`${cpu.toFixed(1)}%`} />
          <Figure label="RAM" value={ram >= 1024 ? `${(ram / 1024).toFixed(1)} GB` : `${Math.round(ram)} MB`} />
          <Figure label="Disk" value={`${diskUsed.toFixed(1)} / ${diskTotal.toFixed(0)} GB`} />
          {host.gpu && <Figure label="GPU" value={host.gpu} />}
          <Sparkline data={history?.aggregate_cpu ?? []} label="CPU, last hour" />
        </OverviewCard>

        <OverviewCard section="logs" level={logLevel}>
          <Figure label="Recent events" value={events.length} />
          <Figure label="Errors" value={`${errorEvents} error event${errorEvents === 1 ? "" : "s"}`} />
          <div className="divide-y divide-border/40">
            {events.slice(0, 3).map((ev, i) => <EventRow key={i} event={ev} />)}
          </div>
        </OverviewCard>
      </div>

      <div className="styx-card rounded-lg p-4">
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          {[
            { label: "Docker", value: host.docker_version ?? "—" },
            { label: "Containers", value: `${c.total}` },
            { label: "Network", value: host.network ?? "styx-portal" },
            { label: "Uptime", value: host.uptime ? formatDuration(host.uptime) : "—" },
          ].map((r) => (
            <div key={r.label}>
              <div className="text-[11px] text-muted-foreground">{r.label}</div>
              <div className="font-mono text-xs text-foreground">{r.value}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
