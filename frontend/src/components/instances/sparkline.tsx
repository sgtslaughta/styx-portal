import { useState, useEffect, useRef, useId } from "react";
import { monotonePath, type Pt } from "@/lib/chart";

interface Series {
  value: number;
  color: string;
  label: string;
}

interface OverlaySparklineProps {
  series: Series[];
  max?: number;
  points?: number;
  height?: number;
  className?: string;
}

function toPts(history: number[], max: number, w: number, h: number, pad: number): Pt[] {
  return history.map((v, i) => [
    (i / (history.length - 1)) * w,
    h - pad - (Math.min(v, max) / max) * (h - pad * 2),
  ]);
}

export function OverlaySparkline({
  series,
  max = 100,
  points = 30,
  height = 32,
  className = "",
}: OverlaySparklineProps) {
  const [histories, setHistories] = useState<number[][]>(() => series.map(() => []));
  const lastValsRef = useRef<string>("");

  useEffect(() => {
    const key = series.map((s) => s.value).join(",");
    if (key === lastValsRef.current) return;
    lastValsRef.current = key;
    setHistories((prev) =>
      series.map((s, i) => {
        const h = [...(prev[i] || []), s.value];
        return h.length > points ? h.slice(-points) : h;
      })
    );
  }, [series, points]);

  const uid = useId().replace(/:/g, "");
  const [hover, setHover] = useState<number | null>(null); // 0..1 across the plot
  const w = 100;
  const pad = 2;
  const allMax = Math.max(max, ...histories.flat(), 1);

  const anyData = histories.some((h) => h.length >= 2);
  if (!anyData) {
    return (
      <div className={`relative ${className}`}>
        <svg width="100%" height={height} viewBox={`0 0 ${w} ${height}`} preserveAspectRatio="none">
          <line x1={0} y1={height / 2} x2={w} y2={height / 2} stroke="var(--muted-foreground)" strokeWidth={1} vectorEffect="non-scaling-stroke" opacity={0.2} strokeDasharray="2 3" />
        </svg>
        <div className="absolute inset-0 flex items-center justify-center gap-3">
          {series.map((s) => (
            <span key={s.label} className="text-[9px] font-mono opacity-40" style={{ color: s.color }}>
              {s.label} —
            </span>
          ))}
        </div>
      </div>
    );
  }

  const idxAt = (hist: number[]) => (hover == null ? hist.length - 1 : Math.round(hover * (hist.length - 1)));

  return (
    <div
      className={`relative ${className}`}
      onMouseMove={(e) => {
        const r = e.currentTarget.getBoundingClientRect();
        setHover(r.width ? Math.min(1, Math.max(0, (e.clientX - r.left) / r.width)) : null);
      }}
      onMouseLeave={() => setHover(null)}
    >
      <svg width="100%" height={height} viewBox={`0 0 ${w} ${height}`} preserveAspectRatio="none" className="overflow-visible">
        <defs>
          {series.map((s, i) => (
            <linearGradient key={s.label} id={`${uid}-${i}`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={s.color} stopOpacity={0.35} />
              <stop offset="100%" stopColor={s.color} stopOpacity={0} />
            </linearGradient>
          ))}
        </defs>
        {histories.map((hist, i) => {
          if (hist.length < 2) return null;
          const s = series[i]!;
          const line = monotonePath(toPts(hist, allMax, w, height, pad));
          return (
            <g key={s.label}>
              <path d={`${line}L${w},${height}L0,${height}Z`} fill={`url(#${uid}-${i})`} stroke="none" />
              <path d={line} fill="none" stroke={s.color} strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" vectorEffect="non-scaling-stroke" />
            </g>
          );
        })}
      </svg>

      {/* Active-point dots (HTML so the stretched viewBox cannot squash them) */}
      {histories.map((hist, i) => {
        if (hist.length < 2) return null;
        const idx = idxAt(hist);
        const y = (toPts(hist, allMax, w, height, pad)[idx]![1] / height) * 100;
        return (
          <span
            key={series[i]!.label}
            className="pointer-events-none absolute h-1.5 w-1.5 -translate-x-1/2 -translate-y-1/2 rounded-full"
            style={{ left: `${(idx / (hist.length - 1)) * 100}%`, top: `${y}%`, backgroundColor: series[i]!.color }}
          />
        );
      })}

      {/* Value label: current values, or the hovered sample in a small tooltip */}
      <div
        role={hover != null ? "tooltip" : undefined}
        className={
          hover != null
            ? "pointer-events-none absolute -top-5 right-0 z-10 flex gap-2 rounded-md border border-border bg-popover px-1.5 py-0.5 shadow-sm"
            : "absolute top-0 right-0 flex gap-2 pr-1"
        }
      >
        {series.map((s, i) => {
          const hist = histories[i] || [];
          const val = hist.length > 0 ? hist[idxAt(hist)]! : 0;
          return (
            <span key={s.label} className="text-[9px] font-mono leading-none" style={{ color: s.color }}>
              {s.label} {Math.round(val)}%
            </span>
          );
        })}
      </div>
    </div>
  );
}
