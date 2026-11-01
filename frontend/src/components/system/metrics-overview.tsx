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
      <OverviewCharts />
      <OverviewLists cf={cf} />
    </div>
  );
}
