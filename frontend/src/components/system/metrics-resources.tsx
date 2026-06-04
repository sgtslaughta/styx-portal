import { useState } from "react";
import { cn } from "@/lib/utils";
import { useInstances, useInstanceStats } from "@/hooks/use-instances";
import { useResourceHistory } from "@/hooks/use-system";
import { Gauge } from "@/components/common/stat-tile";
import { CHART_COLORS } from "@/lib/chart";
import { Clock } from "lucide-react";

const TIME_RANGES = [
  { id: "1h", label: "1H" },
  { id: "6h", label: "6H" },
  { id: "24h", label: "24H" },
] as const;

function TimeSeriesChart({
  label,
  data,
  color,
  max = 100,
  unit = "%",
  height = 80,
}: {
  label: string;
  data: number[];
  color: string;
  max?: number;
  unit?: string;
  height?: number;
}) {
  if (data.length < 2) {
    return (
      <div className="flex items-center justify-center" style={{ height }}>
        <span className="text-[10px] text-muted-foreground/60">Collecting data…</span>
      </div>
    );
  }

  const w = 300;
  const pad = 4;
  const effectiveMax = Math.max(max, ...data, 1);

  const points = data
    .map((v, i) => {
      const x = (i / (data.length - 1)) * w;
      const y = height - pad - (v / effectiveMax) * (height - pad * 2);
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");

  const fillPoints = `0,${height} ${points} ${w},${height}`;
  const currentVal = data[data.length - 1] ?? 0;
  const avgVal = data.reduce((a, b) => a + b, 0) / data.length;
  const peakVal = Math.max(...data);

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <span className="text-[11px] text-muted-foreground font-medium">{label}</span>
        <div className="flex gap-3 text-[10px] tabular-nums">
          <span className="text-muted-foreground">avg <span className="text-foreground">{avgVal.toFixed(1)}{unit}</span></span>
          <span className="text-muted-foreground">peak <span className="text-warning">{peakVal.toFixed(1)}{unit}</span></span>
          <span className="text-muted-foreground">now <span style={{ color }}>{currentVal.toFixed(1)}{unit}</span></span>
        </div>
      </div>
      <svg width="100%" height={height} viewBox={`0 0 ${w} ${height}`} preserveAspectRatio="none" className="rounded">
        {/* Grid lines */}
        {[0.25, 0.5, 0.75].map((pct) => (
          <line
            key={pct}
            x1={0} y1={height * pct} x2={w} y2={height * pct}
            stroke="currentColor" strokeWidth={0.5} className="text-border"
          />
        ))}
        <polygon points={fillPoints} fill={color} opacity={0.06} />
        <polyline fill="none" stroke={color} strokeWidth={1.5} points={points} strokeLinejoin="round" />
        {/* Current value dot */}
        <circle
          cx={w}
          cy={height - pad - (currentVal / effectiveMax) * (height - pad * 2)}
          r={3}
          fill={color}
        />
      </svg>
    </div>
  );
}

function StorageBar({
  label,
  used,
  total,
  color,
}: {
  label: string;
  used: number;
  total: number;
  color: string;
}) {
  const pct = total > 0 ? (used / total) * 100 : 0;
  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between">
        <span className="text-[11px] text-muted-foreground">{label}</span>
        <span className="text-[11px] text-foreground tabular-nums">
          {used.toFixed(1)} / {total.toFixed(1)} GB
        </span>
      </div>
      <div className="h-2 rounded-full bg-secondary overflow-hidden">
        <div
          className="h-full rounded-full transition-all duration-500"
          style={{ width: `${pct}%`, backgroundColor: color, opacity: pct > 80 ? 1 : 0.7 }}
        />
      </div>
    </div>
  );
}

export function MetricsResources() {
  const [range, setRange] = useState<string>("1h");
  const { data: instances } = useInstances();
  const { data: history } = useResourceHistory(range);

  const runningInstances = instances?.filter(
    (i) => i.status === "running" || i.status === "idle"
  ) ?? [];

  const cpuHistory = history?.aggregate_cpu ?? [];
  const ramHistory = history?.aggregate_ram ?? [];
  const storage = history?.storage ?? { volumes_gb: 0, images_gb: 0, total_gb: 0, available_gb: 0 };

  return (
    <div className="space-y-6">
      {/* Time range selector */}
      <div className="flex items-center gap-2">
        <Clock className="h-3.5 w-3.5 text-muted-foreground" />
        <span className="text-[11px] text-muted-foreground mr-1">Range:</span>
        {TIME_RANGES.map((r) => (
          <button
            key={r.id}
            onClick={() => setRange(r.id)}
            className={cn(
              "rounded px-2 py-0.5 text-[11px] font-medium transition-colors",
              range === r.id
                ? "bg-secondary text-foreground"
                : "text-muted-foreground hover:text-foreground/80"
            )}
          >
            {r.label}
          </button>
        ))}
      </div>

      {/* Aggregate Charts */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="styx-card rounded-lg p-4">
          <TimeSeriesChart
            label="System CPU"
            data={cpuHistory}
            color={CHART_COLORS.cpu}
            max={100}
            unit="%"
          />
        </div>
        <div className="styx-card rounded-lg p-4">
          <TimeSeriesChart
            label="System Memory"
            data={ramHistory}
            color={CHART_COLORS.memory}
            max={100}
            unit="%"
          />
        </div>
      </div>

      {/* Per-instance resources */}
      {runningInstances.length > 0 && (
        <div className="styx-card rounded-lg">
          <div className="px-4 py-3 border-b border-border/40">
            <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
              Per-Instance Resources
            </span>
          </div>
          <div className="divide-y divide-border/40">
            {runningInstances.map((inst) => (
              <InstanceResourceRow key={inst.id} instance={inst} />
            ))}
          </div>
        </div>
      )}

      {/* Storage */}
      <div className="styx-card rounded-lg p-4 space-y-4">
        <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
          Storage
        </span>
        <StorageBar
          label="Docker Images"
          used={storage.images_gb}
          total={storage.total_gb}
          color={CHART_COLORS.network}
        />
        <StorageBar
          label="Volumes"
          used={storage.volumes_gb}
          total={storage.total_gb}
          color={CHART_COLORS.memory}
        />
        <StorageBar
          label="System Disk"
          used={storage.total_gb - storage.available_gb}
          total={storage.total_gb}
          color={((storage.total_gb - storage.available_gb) / storage.total_gb) > 0.85 ? "var(--destructive)" : CHART_COLORS.cpu}
        />
      </div>
    </div>
  );
}

function InstanceResourceRow({ instance }: { instance: { id: string; name: string } }) {
  const { data: stats } = useInstanceStats(instance.id, true);

  return (
    <div className="grid grid-cols-[1fr_140px_140px] gap-4 px-4 py-3 items-center">
      <span className="text-xs text-foreground truncate">{instance.name}</span>
      <div>
        <Gauge
          value={Math.min(stats?.cpu_percent ?? 0, 100)}
          max={100}
          label="CPU"
          color={CHART_COLORS.cpu}
          className="text-[10px]"
        />
      </div>
      <div>
        <Gauge
          value={Math.min(stats?.memory_percent ?? 0, 100)}
          max={100}
          label="Memory"
          color={CHART_COLORS.memory}
          className="text-[10px]"
        />
      </div>
    </div>
  );
}
