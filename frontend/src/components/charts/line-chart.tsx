import { useState } from "react";
import { known, runPath, runs, slotVar, type Slot } from "./axis";
import { hideTip, showTip, useTipLifecycle } from "./tooltip";
import { useSize } from "./use-size";
import { Grid, PAD, Plot, plotGeom } from "./plot";

export type LineSeries = { name: string; slot: Slot; data: (number | null)[] };

type Props = {
  series: LineSeries[]; labels: string[]; max?: number;
  fmt?: (v: number) => string; label?: string;
};

/** Multi-series line chart. null values break the line (never drawn as 0); hover shows a crosshair + tooltip. */
export function LineChart({ series, labels, max, fmt = String, label = "Line chart" }: Props) {
  useTipLifecycle();
  const [ref, { w, h }] = useSize<HTMLDivElement>();
  const [hi, setHi] = useState<number | null>(null);
  const n = labels.length;
  const dataMax = Math.max(0, ...series.flatMap((s) => s.data.filter(known)));
  const g = plotGeom(w, h, max ?? dataMax);
  const x = (i: number) => PAD.L + (n > 1 ? (g.iw * i) / (n - 1) : g.iw / 2);
  const step = Math.ceil(n / 6);

  const move = (e: React.MouseEvent<SVGRectElement>) => {
    const r = e.currentTarget.getBoundingClientRect();
    const i = Math.max(0, Math.min(n - 1, Math.round(((e.clientX - r.left) / (r.width || g.iw)) * (n - 1))));
    setHi(i);
    showTip(e, {
      title: labels[i],
      rows: series.map((s) => ({ color: slotVar(s.slot), name: s.name, value: known(s.data[i]) ? fmt(s.data[i]!) : "No data" })),
    });
  };
  const leave = () => { setHi(null); hideTip(); };

  return (
    <div ref={ref} className="relative min-h-[170px] flex-1">
      <Plot w={w} h={h} label={label}>
        <Grid w={w} ticks={g.ticks} y={g.y} fmt={fmt} />
        {labels.map((l, i) => i % step === 0 && (
          <text key={i} x={x(i)} y={h - 6} textAnchor="middle" fontSize={11} fill="var(--muted-foreground)">{l}</text>
        ))}
        {series.map((s) => runs(s.data).map((r, k) => r.length === 1
          ? <circle key={`${s.name}${k}`} cx={x(r[0]!.i)} cy={g.y(r[0]!.v)} r={2.5} fill={slotVar(s.slot)} />
          : <path key={`${s.name}${k}`} d={runPath(r, x, g.y)} fill="none" stroke={slotVar(s.slot)} strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />))}
        {hi !== null && (
          <>
            <line x1={x(hi)} x2={x(hi)} y1={PAD.T} y2={h - PAD.B} stroke="var(--muted-foreground)" strokeDasharray="3 3" />
            {series.map((s) => known(s.data[hi]) && (
              <circle key={s.name} cx={x(hi)} cy={g.y(s.data[hi]!)} r={4} fill={slotVar(s.slot)} stroke="var(--background)" strokeWidth={2} />
            ))}
          </>
        )}
        <rect x={PAD.L} y={0} width={g.iw} height={h} fill="transparent" onMouseMove={move} onMouseLeave={leave} />
      </Plot>
    </div>
  );
}
