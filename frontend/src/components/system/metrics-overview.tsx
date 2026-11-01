import { useQuery } from "@tanstack/react-query";
import { api } from "@/api/client";
import { useSystemMetrics } from "@/hooks/use-system";
import { useCfAnalytics, useOverviewStats } from "@/hooks/use-admin-stats";
import { OverviewTiles } from "./overview-tiles";
import { OverviewCharts } from "./overview-charts";
import { OverviewLists } from "./overview-lists";
import { useAdminPoll } from "@/hooks/use-admin-poll";

/** Monitoring > Overview: five tiles, three equal-height charts, then the lists. */
export function MetricsOverview() {
  const poll = useAdminPoll(30000);
  const { data: stats } = useOverviewStats("24h");
  const { data: metrics } = useSystemMetrics();
  const { data: diag } = useQuery({ queryKey: ["diagnostics"], queryFn: api.getDiagnostics, refetchInterval: poll });
  const cf = useCfAnalytics();
  return (
    <div>
      <OverviewTiles stats={stats} metrics={metrics} diag={diag} />
      <HostLine host={metrics?.host} />
      <OverviewCharts />
      <OverviewLists cf={cf} />
    </div>
  );
}

const fmtUptime = (s?: number) => {
  if (!s) return null;
  const d = Math.floor(s / 86400), h = Math.floor((s % 86400) / 3600);
  return d ? `${d} d ${h} h` : `${h} h`;
};

/** Host facts the old Resources panel showed: GPU, Docker, uptime. Unknown values are omitted. */
function HostLine({ host }: { host?: { gpu?: string; docker_version?: string; uptime?: number } }) {
  const items = [
    ["GPU", host?.gpu && host.gpu !== "None" ? host.gpu : "None detected"],
    ["Docker", host?.docker_version && host.docker_version !== "unknown" ? host.docker_version : null],
    ["Uptime", fmtUptime(host?.uptime)],
  ].filter(([, v]) => v) as [string, string][];
  if (!host || !items.length) return null;
  return (
    <p className="-mt-2 mb-6 flex flex-wrap gap-x-6 gap-y-1 text-[13px] text-muted-foreground">
      {items.map(([k, v]) => <span key={k}>{k} <b className="font-medium text-foreground">{v}</b></span>)}
    </p>
  );
}
