import { useState } from "react";
import { ChartCard } from "@/components/charts/chart-card";
import { LineChart } from "@/components/charts/line-chart";
import { BarChart } from "@/components/charts/bar-chart";
import { HBarStack } from "@/components/charts/hbar-stack";
import { foldStreaming } from "@/components/charts/fold-top";
import { fmtHours, fmtPct, shortDate } from "@/components/charts/format";
import { Seg } from "@/components/settings/seg";
import { useOverviewStats, useStreamingStats } from "@/hooks/use-admin-stats";

const RANGES = [["24h", "24 h"], ["7d", "7 d"], ["30d", "30 d"]] as const;

export function OverviewCharts() {
  const [range, setRange] = useState("24h");
  const { data: stats } = useOverviewStats(range);
  const { data: streaming } = useStreamingStats();
  const folded = foldStreaming(streaming?.rows ?? [], 5);
  const load = stats?.load;
  return (
    <div className="mb-6 grid grid-cols-[repeat(auto-fit,minmax(300px,1fr))] gap-4">
      <ChartCard title="Server load" legend={[{ name: "CPU", slot: "s1" }, { name: "Memory", slot: "s2" }]}
        action={<Seg label="Time range" mini value={range} onChange={setRange} options={RANGES} />}>
        <LineChart label="Server load" max={100} fmt={fmtPct} labels={load?.labels ?? []}
          series={[{ name: "CPU", slot: "s1", data: load?.cpu ?? [] }, { name: "Memory", slot: "s2", data: load?.ram ?? [] }]} />
      </ChartCard>
      <ChartCard title="Sessions per day" hint="last 14 days">
        <BarChart label="Sessions per day" measure="Sessions" fmt={(v) => String(Math.round(v))}
          data={(stats?.sessions_per_day ?? []).map((d) => ({ label: shortDate(d.date), value: d.count }))} />
      </ChartCard>
      <ChartCard title="Streaming time" hint="last 7 days, top 5" legend={folded.series}>
        <HBarStack rows={folded.rows} series={folded.series} measure="Streaming time" fmt={fmtHours} />
      </ChartCard>
    </div>
  );
}
