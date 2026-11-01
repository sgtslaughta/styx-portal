import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api, type TurnUsage } from "@/api/client";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";

export const gb = (bytes: number) => bytes / 1e9;
const fmtGb = (bytes: number) => `${gb(bytes).toFixed(1)} GB`;
const fmtUsd = (n: number) => `$${n.toFixed(2)}`;

/** Static what-if: GB and $ for `hours` per month streaming at `mbps`. */
export function estimateCost(hours: number, mbps: number, freeGb: number, usdPerGb: number) {
  const g = (mbps * 3600 * hours) / 8 / 1000;
  return { gb: g, usd: Math.max(0, g - freeGb) * usdPerGb };
}

function shiftMonth(m: string, delta: number): string {
  const [y, mo] = m.split("-").map(Number) as [number, number];
  const d = new Date(Date.UTC(y, mo - 1 + delta, 1));
  return `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, "0")}`;
}

function UsageTable({ title, rows }: { title: string; rows: { id: string; label: string; bytes: number }[] }) {
  return (
    <div>
      <h4 className="mb-1 text-sm font-medium">{title}</h4>
      {rows.length === 0 ? (
        <p className="text-xs text-muted-foreground">No usage</p>
      ) : (
        <table className="w-full text-sm">
          <tbody>
            {rows.map((r) => (
              <tr key={r.id} className="border-b border-border/40">
                <td className="py-1">{r.label}</td>
                <td className="py-1 text-right tabular-nums">{fmtGb(r.bytes)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-border/50 p-3">
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className="text-lg font-semibold tabular-nums">{value}</div>
    </div>
  );
}

function WhatIf({ u }: { u: TurnUsage | undefined }) {
  const [hours, setHours] = useState("40");
  const [mbps, setMbps] = useState("20");
  const free = u?.free_gb ?? 1000;
  const price = Number(u?.usd_per_gb ?? 0.05);
  const r = estimateCost(Number(hours) || 0, Number(mbps) || 0, free, price);
  const cls = "w-24 rounded border border-border bg-surface px-1 py-0.5";
  return (
    <div className="space-y-2">
      <h4 className="text-sm font-medium">What-if calculator</h4>
      <div className="flex flex-wrap items-center gap-4 text-sm">
        <label className="flex items-center gap-1.5">
          Hours / month
          <input className={cls} type="number" min={0} value={hours} onChange={(e) => setHours(e.target.value)} />
        </label>
        <label className="flex items-center gap-1.5">
          Mbps
          <input className={cls} type="number" min={0} value={mbps} onChange={(e) => setMbps(e.target.value)} />
        </label>
        <span data-testid="whatif-result">
          ≈ {r.gb.toFixed(1)} GB ≈ {fmtUsd(r.usd)}
        </span>
      </div>
    </div>
  );
}

export function TurnCostCard() {
  const [month, setMonth] = useState<string | undefined>(undefined);
  const { data, isLoading, isError } = useQuery({
    queryKey: ["turn-usage", month],
    queryFn: () => api.getTurnUsage(month),
    retry: false,
  });
  const cur = data?.month ?? month;

  return (
    <Card className="styx-card">
      <CardHeader className="pb-4">
        <div className="flex items-center justify-between gap-3">
          <CardTitle>TURN relay usage</CardTitle>
          {cur && (
            <div className="flex items-center gap-2 text-sm">
              <Button size="sm" variant="ghost" aria-label="Previous month" onClick={() => setMonth(shiftMonth(cur, -1))}>
                &lt;
              </Button>
              <span className="tabular-nums">{cur}</span>
              <Button size="sm" variant="ghost" aria-label="Next month" onClick={() => setMonth(shiftMonth(cur, 1))}>
                &gt;
              </Button>
            </div>
          )}
        </div>
      </CardHeader>
      <CardContent className="space-y-5">
        {isLoading ? (
          <p className="text-sm text-muted-foreground">Loading usage...</p>
        ) : isError || !data ? (
          <p className="text-sm text-muted-foreground">usage unavailable</p>
        ) : (
          <>
            {data.over_budget && (
              <p role="alert" className="rounded-md border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-sm">
                TURN budget reached ({data.budget_gb} GB): WebRTC is paused and workstations use
                WebSockets until next month or until the budget is raised.
              </p>
            )}
            <div className="grid grid-cols-2 gap-3 md:grid-cols-3">
              <Stat label="Used this month (metered)" value={fmtGb(data.total_bytes)} />
              {data.cf_egress_bytes != null && (
                <Stat label="Cloudflare actual (egress)" value={fmtGb(data.cf_egress_bytes)} />
              )}
              {data.cf_error && <Stat label="Cloudflare analytics" value="unavailable" />}
              {!!data.budget_gb && (
                <Stat
                  label="Budget used"
                  value={`${Math.min(999, (100 * Math.max(gb(data.total_bytes), gb(data.cf_egress_bytes ?? 0))) / data.budget_gb).toFixed(0)}% of ${data.budget_gb} GB`}
                />
              )}
              <Stat label="Free allowance left" value={`${Math.max(0, data.free_gb - gb(data.total_bytes)).toFixed(1)} GB`} />
              <Stat label="Estimated cost" value={fmtUsd(data.est_usd)} />
              <Stat label="Projected month-end" value={fmtGb(data.projected_bytes)} />
              <Stat label="Projected cost" value={fmtUsd(data.projected_usd)} />
            </div>
            <div className="grid gap-4 md:grid-cols-2">
              <UsageTable
                title="By workstation"
                rows={data.by_workstation.map((w) => ({ id: w.id, label: w.name, bytes: w.bytes }))}
              />
              <UsageTable
                title="By user"
                rows={data.by_user.map((x) => ({ id: x.id, label: x.username, bytes: x.bytes }))}
              />
            </div>
          </>
        )}
        <WhatIf u={data} />
      </CardContent>
    </Card>
  );
}
