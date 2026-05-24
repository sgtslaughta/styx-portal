import { useState, useEffect, useRef } from "react";

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

function buildPolyline(history: number[], max: number, w: number, h: number, pad: number): string {
  return history
    .map((v, i) => {
      const x = (i / (history.length - 1)) * w;
      const y = h - pad - (v / max) * (h - pad * 2);
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
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

  const w = 100;
  const pad = 2;
  const allMax = Math.max(max, ...histories.flat(), 1);

  const anyData = histories.some((h) => h.length >= 2);
  if (!anyData) {
    return (
      <div className={`relative ${className}`}>
        <svg width="100%" height={height} viewBox={`0 0 ${w} ${height}`} preserveAspectRatio="none">
          <line x1={0} y1={height / 2} x2={w} y2={height / 2} stroke="#666" strokeWidth={0.5} opacity={0.2} strokeDasharray="2 3" />
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

  return (
    <div className={`relative ${className}`}>
      <svg width="100%" height={height} viewBox={`0 0 ${w} ${height}`} preserveAspectRatio="none">
        {histories.map((hist, i) => {
          if (hist.length < 2) return null;
          const s = series[i]!;
          const pts = buildPolyline(hist, allMax, w, height, pad);
          const lastVal = hist[hist.length - 1]!;
          const prevVal = hist[hist.length - 2]!;
          const lastY = height - pad - (lastVal / allMax) * (height - pad * 2);
          const fillPts = `0,${height} ${pts} ${w},${height}`;
          const delta = lastVal - prevVal;

          return (
            <g key={s.label}>
              <polygon points={fillPts} fill={s.color} opacity={0.08} />
              <polyline fill="none" stroke={s.color} strokeWidth={1.5} points={pts} strokeLinejoin="bevel" />
              <circle cx={w} cy={lastY} r={2.5} fill={s.color} />
              {Math.abs(delta) > 1 && (
                <text
                  x={w - 8}
                  y={lastY + (delta > 0 ? -5 : 8)}
                  fill={s.color}
                  fontSize={7}
                  fontWeight="bold"
                  textAnchor="end"
                >
                  {delta > 0 ? "▲" : "▼"}
                </text>
              )}
            </g>
          );
        })}
      </svg>

      {/* Legend overlay — top right */}
      <div className="absolute top-0 right-0 flex gap-2 pr-1">
        {series.map((s, i) => {
          const hist = histories[i] || [];
          const val = hist.length > 0 ? hist[hist.length - 1]! : 0;
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
