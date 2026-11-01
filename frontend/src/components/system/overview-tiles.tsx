import { Sparkline } from "@/components/charts/sparkline";
import { fmtPct } from "@/components/charts/format";
import { known } from "@/components/charts/axis";
import type { OverviewStats, Tri } from "@/api/client";

const hourLabel = (i: number, n: number) => {
  const d = new Date(Date.now() - (n - 1 - i) * 3600_000);
  return `${String(d.getHours()).padStart(2, "0")}:00`;
};
const labels = (n: number) => Array.from({ length: n }, (_, i) => hourLabel(i, n));

function peak(series: (number | null)[], fmt: (v: number) => string) {
  const vals = series.filter(known);
  if (!vals.length) return "No history yet";
  const m = Math.max(...vals);
  return `peak ${fmt(m)} at ${hourLabel(series.indexOf(m), series.length)}`;
}

export function Tile({ title, value, note, children, tone }: {
  title: string; value: string; note: string; children?: React.ReactNode; tone?: string;
}) {
  return (
    <div className="min-w-0 rounded-xl border border-border bg-card/55 px-3.5 py-3">
      <span className="text-[13px] text-muted-foreground">{title}</span>
      <b className="block text-2xl font-semibold tabular-nums" style={tone ? { color: tone } : undefined}>{value}</b>
      {children}
      <small className="text-xs text-muted-foreground">{note}</small>
    </div>
  );
}

const CELL: Record<string, string> = {
  ok: "h-3.5 bg-success/70", warn: "h-[22px] bg-warning", fail: "h-[22px] bg-destructive",
};
const CELL_NAME: Record<string, string> = { ok: "All checks passing", warn: "Warning", fail: "Failing" };

/** 24 hourly cells; null = no data, shown as a neutral empty cell (never green). */
export function HealthStrip({ hours }: { hours: (Tri | null)[] }) {
  const lb = labels(hours.length);
  return (
    <div className="my-0.5 grid h-[34px] items-end gap-0.5" style={{ gridTemplateColumns: `repeat(${hours.length || 24}, 1fr)` }}
      role="img" aria-label="Health, last 24 hours, one cell per hour">
      {hours.map((h, i) => (
        <i key={i} title={`${lb[i]}: ${h ? CELL_NAME[h] : "No data"}`}
          className={`block rounded-sm ${h ? CELL[h] : "h-3.5 border border-dashed border-border bg-transparent"}`} />
      ))}
    </div>
  );
}

type MetricsLite = { host_ram_total_mb?: number | null; disk_used_gb: number; disk_total_gb: number } | undefined;
type Diag = { checks: { ok: boolean }[] } | undefined;

export function OverviewTiles({ stats, metrics, diag }: { stats: OverviewStats | undefined; metrics: MetricsLite; diag: Diag }) {
  const t = stats?.tiles;
  const lb = labels(24);
  const pct = (n: number | null | undefined) => (known(n) ? fmtPct(n) : "—");
  const ramGb = (metrics?.host_ram_total_mb && t && known(t.ram.now))
    ? `${((metrics.host_ram_total_mb * t.ram.now) / 100 / 1024).toFixed(1)} of ${Math.round(metrics.host_ram_total_mb / 1024)} GB` : "Memory in use";
  const warns = (stats?.health_hours ?? []).filter((h) => h === "warn" || h === "fail").length;
  const checks = diag?.checks ?? [];
  const passing = checks.filter((c) => c.ok).length;
  const liveMax = Math.max(0, ...(t?.live.series.filter(known) ?? []));
  return (
    <div className="mb-6 grid grid-cols-[repeat(auto-fit,minmax(170px,1fr))] gap-3">
      <Tile title="CPU" value={pct(t?.cpu.now)} note={peak(t?.cpu.series ?? [], fmtPct)}>
        <Sparkline data={t?.cpu.series ?? []} name="CPU" slot="s1" labels={lb} fmt={fmtPct} min={0} max={100} />
      </Tile>
      <Tile title="Memory" value={pct(t?.ram.now)} note={ramGb}>
        <Sparkline data={t?.ram.series ?? []} name="Memory" slot="s2" labels={lb} fmt={fmtPct} min={0} max={100} />
      </Tile>
      <Tile title="Disk" value={pct(t?.disk.now)} note={metrics ? `${Math.round(metrics.disk_used_gb)} of ${Math.round(metrics.disk_total_gb)} GB used` : "Disk in use"}>
        <Sparkline data={t?.disk.series ?? []} name="Disk" slot="s3" labels={lb} fmt={fmtPct} min={0} max={100} />
      </Tile>
      <Tile title="Live sessions" value={known(t?.live.now) ? String(t!.live.now) : "—"} note={liveMax ? `peak ${liveMax} in 24 h` : "None in the last 24 h"}>
        <Sparkline data={t?.live.series ?? []} name="Live sessions" slot="s4" labels={lb} fmt={(v) => String(Math.round(v))} min={0} />
      </Tile>
      <Tile title="Health" value={checks.length ? `${passing}/${checks.length}` : "—"}
        tone={checks.length && passing < checks.length ? "var(--destructive)" : "var(--success-foreground)"}
        note={warns ? `${warns} hour${warns === 1 ? "" : "s"} with warnings today` : "No warnings today"}>
        <HealthStrip hours={stats?.health_hours ?? Array(24).fill(null)} />
      </Tile>
    </div>
  );
}
