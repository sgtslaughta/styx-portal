import { useEffect, useRef, useState } from "react";
import { Sparkline } from "@/components/charts/sparkline";
import type { Slot } from "@/components/charts/axis";

interface Series { value: number; color: string; label: string }
interface Props { series: Series[]; max?: number; points?: number; height?: number; className?: string }

const SLOTS: Slot[] = ["s1", "s2"];

/** Live instance stats: accumulates polled values client-side and draws them with the shared Sparkline. */
export function OverlaySparkline({ series, max = 100, points = 30, height = 32, className = "" }: Props) {
  const [hist, setHist] = useState<number[][]>(() => series.map(() => []));
  const last = useRef("");
  useEffect(() => {
    const key = series.map((s) => s.value).join(",");
    if (key === last.current) return;
    last.current = key;
    setHist((prev) => series.map((s, i) => [...(prev[i] ?? []), s.value].slice(-points)));
  }, [series, points]);

  const cur = (i: number) => hist[i]?.[hist[i]!.length - 1];
  return (
    <div className={`relative ${className}`} style={{ height }}>
      {series.map((s, i) => (
        <div key={s.label} className={i ? "pointer-events-none absolute inset-0" : ""}>
          <Sparkline data={hist[i] ?? []} name={s.label} slot={SLOTS[i % 2]} min={0} max={max} height={height}
            bare={i > 0} fmt={(v) => `${Math.round(v)}%`} />
        </div>
      ))}
      <div className="pointer-events-none absolute right-0 top-0 flex gap-2 pr-1">
        {series.map((s, i) => (
          <span key={s.label} className="font-mono text-[9px] leading-none text-muted-foreground">
            {s.label} {cur(i) === undefined ? "—" : `${Math.round(cur(i)!)}%`}
          </span>
        ))}
      </div>
    </div>
  );
}
