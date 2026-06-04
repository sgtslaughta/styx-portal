import { motion } from "framer-motion";
import { useInstances } from "@/hooks/use-instances";
import { useSystemMetrics } from "@/hooks/use-system";
import {
  Activity,
  Cpu,
  MemoryStick,
  HardDrive,
  AlertTriangle,
} from "lucide-react";
import { StatTile } from "@/components/common/stat-tile";
import { formatDuration } from "@/lib/utils";

function EventRow({ event }: { event: { type: string; instance: string; time: string; details?: string } }) {
  const typeColors: Record<string, string> = {
    started: "text-emerald-400",
    stopped: "text-muted-foreground",
    error: "text-destructive",
    restarted: "text-blue-400",
    paused: "text-warning",
    created: "text-purple-400",
  };

  return (
    <div className="flex items-center gap-3 py-2 px-3 rounded-md hover:bg-muted/30 transition-colors group">
      <div className={`h-1.5 w-1.5 rounded-full ${typeColors[event.type]?.replace("text-", "bg-") ?? "bg-muted-foreground"}`} />
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

export function MetricsOverview() {
  const { data: instances } = useInstances();
  const { data: metrics } = useSystemMetrics();

  const counts = {
    running: 0,
    stopped: 0,
    error: 0,
    paused: 0,
    total: 0,
  };
  instances?.forEach((inst) => {
    counts.total++;
    if (inst.status === "running" || inst.status === "idle") counts.running++;
    else if (inst.status === "error") counts.error++;
    else if (inst.status === "paused") counts.paused++;
    else counts.stopped++;
  });

  const events = metrics?.recent_events ?? [];
  const hostInfo = metrics?.host ?? {};
  const aggregateCpu = metrics?.aggregate_cpu ?? 0;
  const aggregateRam = metrics?.aggregate_ram_mb ?? 0;
  const diskUsed = metrics?.disk_used_gb ?? 0;
  const diskTotal = metrics?.disk_total_gb ?? 0;

  return (
    <div className="space-y-6">
      {/* Health banner */}
      {counts.error > 0 && (
        <motion.div
          initial={{ opacity: 0, height: 0 }}
          animate={{ opacity: 1, height: "auto" }}
          className="flex items-center gap-3 rounded-lg border border-destructive/30 bg-destructive/5 px-4 py-3"
        >
          <AlertTriangle className="h-4 w-4 text-destructive" />
          <span className="text-sm text-destructive/80">
            {counts.error} instance{counts.error > 1 ? "s" : ""} in error state
          </span>
        </motion.div>
      )}

      {/* Stat cards grid */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <StatTile
          label="Running"
          value={counts.running}
          sub={`of ${counts.total}`}
          icon={Activity}
        />
        <StatTile
          label="CPU Usage"
          value={`${aggregateCpu.toFixed(1)}%`}
          sub="aggregate"
          icon={Cpu}
        />
        <StatTile
          label="Memory"
          value={aggregateRam >= 1024 ? `${(aggregateRam / 1024).toFixed(1)} GB` : `${Math.round(aggregateRam)} MB`}
          sub="allocated"
          icon={MemoryStick}
        />
        <StatTile
          label="Disk"
          value={`${diskUsed.toFixed(1)} GB`}
          sub={diskTotal > 0 ? `of ${diskTotal.toFixed(0)} GB` : undefined}
          icon={HardDrive}
        />
      </div>

      {/* Two-column: Events + Host Info */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Recent Events */}
        <div className="lg:col-span-2 rounded-lg border border-border bg-card">
          <div className="flex items-center justify-between px-4 py-3 border-b border-border/40">
            <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
              Recent Events
            </span>
            <span className="text-[10px] text-muted-foreground/60">{events.length} events</span>
          </div>
          <div className="max-h-[280px] overflow-y-auto divide-y divide-border/40">
            {events.length === 0 ? (
              <div className="py-8 text-center text-xs text-muted-foreground/60">No recent events</div>
            ) : (
              events.map((ev, i) => <EventRow key={i} event={ev} />)
            )}
          </div>
        </div>

        {/* Host Info */}
        <div className="rounded-lg border border-border bg-card">
          <div className="px-4 py-3 border-b border-border/40">
            <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
              Host
            </span>
          </div>
          <div className="p-4 space-y-3">
            {[
              { label: "Docker", value: hostInfo.docker_version ?? "—" },
              { label: "GPU", value: hostInfo.gpu ?? "None" },
              { label: "Containers", value: `${counts.total}` },
              { label: "Network", value: hostInfo.network ?? "styx-portal" },
              { label: "Uptime", value: hostInfo.uptime ? formatDuration(hostInfo.uptime) : "—" },
            ].map((row) => (
              <div key={row.label} className="flex items-center justify-between">
                <span className="text-[11px] text-muted-foreground">{row.label}</span>
                <span className="text-xs text-foreground font-mono">{row.value}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
