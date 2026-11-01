import { useState } from "react";
import { known, runPath, runs, slotVar, type Slot } from "./axis";
import { hideTip, showTip, useTipLifecycle } from "./tooltip";
import { useSize } from "./use-size";

type Props = {
  data: (number | null)[]; name: string; slot?: Slot; fmt?: (v: number) => string; labels?: string[];
  min?: number; max?: number; height?: number; /** no hover/area: for stacking a second line over another sparkline */ bare?: boolean;
};

/** Tile sparkline: 2px line + soft area, last point dotted, hover names the measure. Nulls break the line. */
export function Sparkline({ data, name, slot = "s1", fmt = String, labels, min, max, height = 34, bare }: Props) {
  useTipLifecycle();
  const [ref, { w }] = useSize<HTMLDivElement>(120, height);
  const [hi, setHi] = useState<number | null>(null);
  const vals = data.filter(known);
  if (!vals.length) {
    if (bare) return null;
    return <div className="flex items-center text-xs text-muted-foreground" style={{ height }}>No data yet</div>;
  }
  const pad = 3, color = slotVar(slot);
  const mn = min ?? Math.min(...vals), mx = max ?? Math.max(...vals);
  const n = data.length;
  const x = (i: number) => (n > 1 ? (w * i) / (n - 1) : w / 2);
  const y = (v: number) => height - pad - ((height - 2 * pad) * (v - mn)) / (mx - mn || 1);
  const rs = runs(data);
  const lastI = data.map(known).lastIndexOf(true);
  const dotI = hi !== null && known(data[hi]) ? hi : lastI;

  const move = (e: React.MouseEvent<SVGSVGElement>) => {
    const r = e.currentTarget.getBoundingClientRect();
    const i = Math.max(0, Math.min(n - 1, Math.round(((e.clientX - r.left) / (r.width || w)) * (n - 1))));
    setHi(i);
    showTip(e, { title: labels?.[i], rows: [{ name, value: known(data[i]) ? fmt(data[i]!) : "No data" }] });
  };

  return (
    <div ref={ref} className="my-0.5 w-full" style={{ height }}>
      <svg width={w} height={height} viewBox={`0 0 ${w} ${height}`} className="block overflow-visible" role="img" aria-label={`${name} trend`}
        style={bare ? { pointerEvents: "none" } : undefined}
        onMouseMove={bare ? undefined : move} onMouseLeave={bare ? undefined : () => { setHi(null); hideTip(); }}>
        {!bare && rs.filter((r) => r.length > 1).map((r, k) => (
          <path key={`a${k}`} d={`${runPath(r, x, y)}L${x(r[r.length - 1]!.i)},${height}L${x(r[0]!.i)},${height}Z`} fill={color} opacity={0.12} />
        ))}
        {rs.filter((r) => r.length > 1).map((r, k) => (
          <path key={k} d={runPath(r, x, y)} fill="none" stroke={color} strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
        ))}
        {rs.filter((r) => r.length === 1 && r[0]!.i !== dotI).map((r) => <circle key={`p${r[0]!.i}`} cx={x(r[0]!.i)} cy={y(r[0]!.v)} r={2} fill={color} />)}
        {dotI >= 0 && <circle cx={x(dotI)} cy={y(data[dotI]!)} r={3} fill={color} />}
      </svg>
    </div>
  );
}
