import { useState } from "react";
import { ApiError } from "@/api/client";
import { useRelayStats } from "@/hooks/use-admin-stats";
import { goSection } from "@/lib/section-nav";
import { ChartCard } from "@/components/charts/chart-card";
import { BarChart } from "@/components/charts/bar-chart";
import { HBars } from "@/components/charts/hbar-stack";
import { foldTop } from "@/components/charts/fold-top";
import { fmtGb, fmtUsd, shortDate, shortMonth } from "@/components/charts/format";
import { Seg } from "@/components/settings/seg";
import { Tile } from "./overview-tiles";
import { SectionHead } from "@/components/common/section-head";

const PERIODS = [["last", "Last month"], ["this", "This month"], ["6m", "6 months"]] as const;
const REASONS: Record<string, { label: string; sub?: string }> = {
  strict_nat: { label: "Strict NAT", sub: "work network" }, firewall: { label: "Firewall", sub: "UDP blocked" },
  mobile: { label: "Mobile data" }, unknown: { label: "Unknown" },
};
const reasonRow = (x: { reason: string; sessions: number }) => ({ label: REASONS[x.reason]?.label ?? x.reason.replace(/_/g, " "), sub: REASONS[x.reason]?.sub, value: x.sessions });

const top5 = (rows: { name: string; gb: number }[]) =>
  foldTop(rows, 5, (r) => r.gb).map((r) =>
    "others" in r ? { label: `Others · ${r.others.length} more`, value: r.others.reduce((a, x) => a + x.gb, 0), others: true } : { label: r.name, value: r.gb, others: false });

export function RelayCostPage() {
  const [period, setPeriod] = useState<string>("this");
  const [table, setTable] = useState(false);
  const { data: r, error, isLoading } = useRelayStats(period);

  if (error instanceof ApiError && error.status === 404) {
    return (
      <div className="rounded-xl border border-border bg-card/55 p-6 text-sm text-muted-foreground">
        Connect Cloudflare analytics in <button type="button" className="text-primary hover:underline" onClick={() => goSection("streaming")}>Streaming</button> to see relay cost.
      </div>
    );
  }
  if (isLoading || !r) return <p className="text-sm text-muted-foreground">{error ? "Relay data is unavailable right now." : "Loading…"}</p>;

  const byUser = top5(r.by_user), byWs = top5(r.by_workstation);
  const reasons = r.reasons.map(reasonRow);
  const pctUsed = Math.min(100, (r.used_gb / (r.free_gb || 1)) * 100);
  const free = r.est_usd === 0;
  const budget = r.budget_gb ? r.budget_gb / (period === "6m" ? 6 : 1) : null;
  const refLine = budget ? { value: budget, label: `Budget alert at ${fmtGb(budget)}` } : undefined;
  const rowsAll = [
    ...r.by_user.map((x) => ["User", x.name, fmtGb(x.gb)]),
    ...r.by_workstation.map((x) => ["Workstation", x.name, fmtGb(x.gb)]),
    ...r.reasons.map((x) => ["Relay reason", REASONS[x.reason]?.label ?? x.reason, `${x.sessions} sessions`]),
    ...r.monthly.map((x) => ["Month", shortMonth(x.month), fmtGb(x.gb)]),
  ];

  return (
    <div>
      <SectionHead title="Relay cost" action={<Seg label="Period" value={period} onChange={setPeriod} options={PERIODS} />} />
      <div className="mb-6 grid grid-cols-[repeat(auto-fit,minmax(170px,1fr))] gap-3">
        <Tile title="Relay data used" value={fmtGb(r.used_gb)} note={`of ${fmtGb(r.free_gb)} free`}>
          <span className="track my-1.5"><i style={{ width: `${pctUsed}%`, minWidth: 4, background: "var(--obol-solid)" }} /></span>
        </Tile>
        <Tile title="Projected month-end" value={fmtGb(r.projected_gb)} note="at the current daily rate" />
        <Tile title="Estimated cost" value={fmtUsd(r.est_usd)} note="past the free tier" />
        <Tile title="Budget left" value={fmtUsd(Math.max(0, r.budget_usd - r.est_usd))} note={`of ${fmtUsd(r.budget_usd)} / month`} />
        <Tile title="Relayed sessions" value={`${Math.round(r.relayed_pct)}%`} note="of sessions; the rest went direct" />
      </div>
      <div className="mb-4 grid gap-4 lg:grid-cols-[2fr_1fr]">
        <ChartCard title="Relay data per day" hint="last 30 days">
          <BarChart label="Relay data per day" measure="Relay data" fmt={fmtGb} data={r.daily.map((d) => ({ label: shortDate(d.date), value: d.gb }))} />
        </ChartCard>
        <ChartCard title="Relay data by month" hint={free ? "all within the free tier, $0 billed" : undefined}>
          <BarChart label="Relay data by month" measure="Relay data" fmt={fmtGb}
            refLine={refLine}
            data={r.monthly.map((m) => ({ label: shortMonth(m.month), value: m.gb }))} />
        </ChartCard>
      </div>
      <div className="mb-4 grid grid-cols-[repeat(auto-fit,minmax(280px,1fr))] gap-4">
        <ChartCard title="By user" hint="top 5"><HBars rows={byUser} measure="Relay data" fmt={fmtGb} /></ChartCard>
        <ChartCard title="By workstation" hint="top 5"><HBars rows={byWs} measure="Relay data" fmt={fmtGb} slot="s2" /></ChartCard>
        <ChartCard title="Why sessions were relayed" hint="sessions"><HBars rows={reasons} measure="Sessions" slot="s3" fmt={(v) => String(Math.round(v))} /></ChartCard>
      </div>
      <button type="button" aria-expanded={table} className="mb-2 text-[13.5px] text-primary hover:underline" onClick={() => setTable((t) => !t)}>Show as table</button>
      {table && (
        <table className="dense full">
          <thead><tr><th>Breakdown</th><th>Name</th><th>Relay data</th></tr></thead>
          <tbody>{rowsAll.map(([g, n, v], i) => <tr key={i}><td>{g}</td><td>{n}</td><td className="tabular-nums">{v}</td></tr>)}</tbody>
        </table>
      )}
    </div>
  );
}
