import type { ReactNode } from "react";
import { niceTicks } from "./axis";

export const PAD = { L: 40, R: 8, T: 8, B: 22 };

/** Frame geometry + dashed grid + y axis labels shared by line and bar charts. */
export function plotGeom(w: number, h: number, max: number) {
  const iw = Math.max(1, w - PAD.L - PAD.R), ih = Math.max(1, h - PAD.T - PAD.B);
  const ticks = niceTicks(max);
  const top = ticks[ticks.length - 1]!;
  return { iw, ih, ticks, top, y: (v: number) => h - PAD.B - (ih * v) / top };
}

export function Grid({ w, ticks, y, fmt }: {
  w: number; ticks: number[]; y: (v: number) => number; fmt: (v: number) => string;
}) {
  return (
    <>
      {ticks.map((t, i) => (
        <g key={t}>
          <line x1={PAD.L} x2={w - PAD.R} y1={y(t)} y2={y(t)} stroke="var(--border)" strokeDasharray={i ? "2 4" : undefined} />
          <text x={PAD.L - 6} y={y(t) + 4} textAnchor="end" fontSize={11} fill="var(--muted-foreground)" style={{ fontVariantNumeric: "tabular-nums" }}>{fmt(t)}</text>
        </g>
      ))}
    </>
  );
}

export function Plot({ svgRef, w, h, label, children }: {
  svgRef?: React.Ref<SVGSVGElement>; w: number; h: number; label: string; children: ReactNode;
}) {
  return (
    <svg ref={svgRef} width={w} height={h} viewBox={`0 0 ${w} ${h}`} role="img" aria-label={label}
      className="absolute inset-0 block overflow-visible">
      {children}
    </svg>
  );
}
