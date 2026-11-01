import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { api } from "@/api/client";
import { useRailRows, type RailRow } from "@/hooks/use-rail-data";
import { useRelayStats } from "@/hooks/use-admin-stats";
import { goSection } from "@/lib/section-nav";
import { fmtGb, fmtUsd } from "@/components/charts/format";
import { SectionHead } from "@/components/common/section-head";
import { ConfirmDialog } from "@/components/common/confirm-dialog";
import { Dot } from "@/components/common/dot";
import { LoadError } from "@/components/common/load-error";

const GHOST = "rounded-lg border border-border px-3 py-1 text-[13px] hover:bg-muted";

type ListProps = { rows: RailRow[]; ready: boolean; error?: boolean; retry: () => void };

export function NeedsLook({ rows, ready, error, retry }: ListProps) {
  return (
    <section className="rounded-xl border border-border bg-card/55 p-4" aria-label="Needs a look">
      <SectionHead title="Needs a look" />
      {error && !rows.length ? <LoadError retry={retry} />
        : !ready && !rows.length ? <p className="text-[13px] text-muted-foreground">Loading…</p>
        : !rows.length ? <p className="text-[13px] text-muted-foreground">All clear</p>
        : (
          <ul className="grid list-none gap-3 p-0 text-sm">
            {rows.map((r) => (
              <li key={r.id} className="flex items-start gap-2.5">
                <Dot tone={r.tone} />
                <span className="flex-1">{r.text}{r.sub && <small className="block text-[12.5px] text-muted-foreground">{r.sub}</small>}</span>
                {r.action && <button type="button" className={GHOST} onClick={() => goSection(r.action!.section)}>{r.action.label}</button>}
              </li>
            ))}
          </ul>
        )}
    </section>
  );
}

export function RelayCard() {
  const { data: r, isError } = useRelayStats("this");
  return (
    <section className="rounded-xl border border-border bg-card/55 p-4" aria-label="Relay cost">
      <SectionHead title="Relay cost" note="Cloudflare analytics" />
      {isError ? <p className="text-[13px] text-muted-foreground">Relay data is unavailable right now.</p> : !r ? <p className="text-[13px] text-muted-foreground">Loading…</p> : (
        <div className="usage">
          <div className="u-head"><span>Relay data this month</span><b className="tabular-nums text-foreground">{fmtGb(r.used_gb)}</b><span className="text-xs">of {fmtGb(r.free_gb)} free</span></div>
          <span className="track"><i style={{ width: `${Math.min(100, (r.used_gb / (r.free_gb || 1)) * 100)}%`, minWidth: 4 }} /></span>
          <div className="flex flex-wrap gap-x-4 gap-y-1 text-[13px]">
            <span>Projected <b className="tabular-nums text-foreground">{fmtGb(r.projected_gb)}</b></span>
            <span>Estimated cost <b className="tabular-nums text-foreground">{fmtUsd(r.est_usd)}</b></span>
            <span>Budget <b className="tabular-nums text-foreground">{fmtUsd(r.budget_usd)}</b></span>
            <a href="#relay-cost" className="ml-auto text-primary hover:underline" onClick={(e) => { e.preventDefault(); goSection("relay-cost"); }}>Breakdown</a>
          </div>
        </div>
      )}
    </section>
  );
}

export function ActiveNow({ rows, ready, error, retry }: ListProps) {
  const qc = useQueryClient();
  const [ending, setEnding] = useState<RailRow | null>(null);
  const end = async (r: RailRow) => {
    try {
      await api.stopInstance(r.instanceId!);
      qc.invalidateQueries({ queryKey: ["instances"] });
    } catch (e) {
      toast.error(`Couldn't end ${r.text}: ${(e as Error).message}`);
    }
  };
  return (
    <section className="rounded-xl border border-border bg-card/55 p-4" aria-label="Active now">
      <SectionHead title="Active now" />
      {error && !rows.length ? <LoadError retry={retry} /> : !rows.length ? <p className="text-[13px] text-muted-foreground">{ready ? "Nothing running" : "Loading…"}</p> : (
        <table className="dense"><tbody>
          {rows.map((r) => (
            <tr key={r.id}>
              <td><strong>{r.text}</strong></td>
              <td className="text-muted-foreground">{r.kind}</td>
              <td className="acts">{r.instanceId && <button type="button" className={GHOST} onClick={() => setEnding(r)}>End</button>}</td>
            </tr>
          ))}
        </tbody></table>
      )}
      <ConfirmDialog open={!!ending} onOpenChange={(o) => !o && setEnding(null)}
        title={`End ${ending?.text ?? ""}?`} description="This stops the container. Unsaved work in it is lost."
        variant="destructive" confirmLabel="End"
        onConfirm={() => { const r = ending; setEnding(null); if (r) void end(r); }} />
    </section>
  );
}

export function OverviewLists({ cf }: { cf: boolean }) {
  const { active, check, activeReady, checkReady, activeError, checkError, retry } = useRailRows();
  return (
    <div className="grid grid-cols-[repeat(auto-fit,minmax(300px,1fr))] gap-4">
      <NeedsLook rows={check} ready={checkReady} error={checkError} retry={retry} />
      {cf && <RelayCard />}
      <ActiveNow rows={active} ready={activeReady} error={activeError} retry={retry} />
    </div>
  );
}
