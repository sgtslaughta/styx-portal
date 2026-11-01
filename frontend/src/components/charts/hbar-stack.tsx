import { slotVar, type Slot } from "./axis";
import { hideTip, showTip, useTipLifecycle } from "./tooltip";

type Series = { name: string; slot: Slot };
export type HRow = { label: string; sub?: string; parts: Record<string, number> };
type Props = { rows: HRow[]; series: Series[]; measure: string; fmt?: (v: number) => string; empty?: string };

const total = (r: HRow, series: Series[]) => series.reduce((a, s) => a + (r.parts[s.name] ?? 0), 0);

/** Horizontal bars, optionally stacked by series: 2px gap between segments, rounded outer end, value in ink colour. */
export function HBarStack({ rows, series, measure, fmt = String, empty = "No data yet" }: Props) {
  useTipLifecycle();
  const max = Math.max(0, ...rows.map((r) => total(r, series)));
  if (!rows.length || max <= 0) return <p className="py-6 text-center text-[13px] text-muted-foreground">{empty}</p>;
  return (
    <div className="grid gap-1 pt-1">
      {rows.map((r) => {
        const segs = series.filter((s) => (r.parts[s.name] ?? 0) > 0);
        return (
          <div key={r.label} className="-mx-1.5 grid grid-cols-[minmax(70px,110px)_1fr_64px] items-center gap-2.5 rounded-md px-1.5 py-1 text-[13px] hover:bg-primary/10">
            <span className="truncate">{r.label}{r.sub && <small className="block text-[11.5px] text-muted-foreground">{r.sub}</small>}</span>
            <span className="flex h-2.5 min-w-0 gap-0.5 overflow-hidden">
              {segs.map((s, i) => (
                <i key={s.name} className="block h-full min-w-[3px] shrink"
                  style={{ width: `${((r.parts[s.name] ?? 0) / max) * 100}%`, background: slotVar(s.slot), borderRadius: i === segs.length - 1 ? "0 4px 4px 0" : 0 }}
                  onMouseMove={(e) => showTip(e, { title: r.label, rows: [{ color: slotVar(s.slot), name: s.name === "Others" || series.length > 2 ? s.name : measure, value: fmt(r.parts[s.name]!) }] })}
                  onMouseLeave={hideTip} />
              ))}
            </span>
            <span className="text-right tabular-nums">{fmt(total(r, series))}</span>
          </div>
        );
      })}
    </div>
  );
}

/** Single-series convenience: rows {label, value}. */
export function HBars({ rows, slot = "s1", measure, fmt, empty }: {
  rows: { label: string; value: number; sub?: string; others?: boolean }[]; slot?: Slot; measure: string; fmt?: (v: number) => string; empty?: string;
}) {
  const hasOthers = rows.some((r) => r.others);
  const series: Series[] = [{ name: measure, slot }, ...(hasOthers ? [{ name: "Others", slot: "s0" as Slot }] : [])];
  return (
    <HBarStack measure={measure} fmt={fmt} empty={empty} series={series}
      rows={rows.map((r) => ({ label: r.label, sub: r.sub, parts: { [r.others ? "Others" : measure]: r.value } }))} />
  );
}
