import { useQuery } from "@tanstack/react-query";
import { api } from "@/api/client";

const gb = (b: number) => b / 1e9;
const fmt = (b: number) => `${gb(b).toFixed(1)} GB`;

export function TurnUsageMeter() {
  const { data: u, isError } = useQuery({ queryKey: ["turn-usage", undefined], queryFn: () => api.getTurnUsage(), retry: false });
  if (isError) return <p className="text-sm text-muted-foreground">Relay usage unavailable</p>;
  if (!u) return null;
  const used = Math.max(gb(u.total_bytes), gb(u.cf_egress_bytes ?? 0));
  const pct = u.free_gb ? Math.min(100, (100 * used) / u.free_gb) : 0;
  return (
    <div className="usage">
      <div className="u-head"><span>Relay data this month</span><b className="tabular-nums">{used.toFixed(1)} GB</b><span>of {u.free_gb.toLocaleString()} GB free</span></div>
      <span className="track" role="progressbar" aria-label="Relay data used" aria-valuenow={Math.round(pct)} aria-valuemin={0} aria-valuemax={100}>
        <i style={{ width: `${pct}%`, minWidth: 4 }} />
      </span>
      <div className="u-foot">
        <span>Projected <b className="tabular-nums">{fmt(u.projected_bytes)}</b></span>
        <span>Estimated cost <b className="tabular-nums">${u.est_usd.toFixed(2)}</b></span>
        {!!u.budget_gb && <span>Budget <b className="tabular-nums">{u.budget_gb} GB / month</b></span>}
      </div>
      {u.over_budget && <p role="alert">Budget reached: workstations use WebSockets until next month or until the budget is raised.</p>}
    </div>
  );
}
