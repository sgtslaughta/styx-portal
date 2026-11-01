import { useId } from "react";
import { known, slotVar, type Slot } from "./axis";
import { hideTip, showTip } from "./tooltip";
import { useSize } from "./use-size";
import { Grid, PAD, Plot, plotGeom } from "./plot";

export type Bar = { label: string; value: number | null; note?: string; ghost?: boolean };
type Props = {
  data: Bar[]; slot?: Slot; measure: string; fmt?: (v: number) => string;
  refLine?: { value: number; label: string }; label?: string;
};

/** Single-series vertical bars: 4px rounded tops, ghost (projected) bars textured, optional dashed reference line. */
export function BarChart({ data, slot = "s1", measure, fmt = String, refLine, label = "Bar chart" }: Props) {
  const [box, { w, h }] = useSize<HTMLDivElement>();
  const uid = useId().replace(/:/g, "");
  const color = slotVar(slot);
  const max = Math.max(0, refLine?.value ?? 0, ...data.map((d) => d.value ?? 0));
  const g = plotGeom(w, h, max);
  const n = data.length, bw = g.iw / Math.max(n, 1), base = h - PAD.B;
  const every = Math.ceil(n / 8);

  return (
    <div ref={box} className="relative min-h-[170px] flex-1">
      <Plot w={w} h={h} label={label}>
        <defs>
          <pattern id={`${uid}t`} width={6} height={6} patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
            <rect width={6} height={6} fill={color} opacity={0.18} />
            <line x1={0} y1={0} x2={0} y2={6} stroke={color} strokeWidth={2} />
          </pattern>
        </defs>
        <Grid w={w} ticks={g.ticks} y={g.y} fmt={fmt} />
        {data.map((d, i) => {
          const x = PAD.L + i * bw + 1, bwid = Math.max(2, bw - 2);
          const top = known(d.value) ? g.y(d.value) : base, bh = base - top, r = Math.min(4, bwid / 2, bh);
          return (
            <g key={i}>
              {known(d.value) && bh > 0 && (
                <path d={`M${x},${base}V${top + r}q0,-${r} ${r},-${r}h${bwid - 2 * r}q${r},0 ${r},${r}V${base}Z`}
                  fill={d.ghost ? `url(#${uid}t)` : color} />
              )}
              {i % every === 0 && <text x={x + bwid / 2} y={h - 6} textAnchor="middle" fontSize={11} fill="var(--muted-foreground)">{d.label}</text>}
              <rect x={PAD.L + i * bw} y={PAD.T} width={bw} height={g.ih} fill="transparent"
                onMouseMove={(e) => showTip(e, {
                  title: d.label,
                  rows: [{ name: d.ghost ? `Projected ${measure.toLowerCase()}` : measure, value: known(d.value) ? fmt(d.value) : "No data" }],
                  note: d.note,
                })}
                onMouseLeave={hideTip} />
            </g>
          );
        })}
        {refLine && (
          <>
            <line x1={PAD.L} x2={w - PAD.R} y1={g.y(refLine.value)} y2={g.y(refLine.value)} stroke="var(--muted-foreground)" strokeDasharray="4 4" />
            <text x={w - PAD.R} y={g.y(refLine.value) - 5} textAnchor="end" fontSize={11} fill="var(--foreground)">{refLine.label}</text>
          </>
        )}
      </Plot>
    </div>
  );
}
