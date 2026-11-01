import { useEffect, useRef, useState } from "react";
import { createWater, type Water } from "@/lib/effects/water";
import { useCanvasEffect } from "@/hooks/use-canvas-effect";
import { GlassButton } from "@/components/ui/glass-button";
import { statusMeta } from "@/lib/status";
import type { RecentItem } from "@/lib/recents";

/** Thumbnail that refracts like water under the cursor; no water if the image is missing or fails. */
function Shot({ item }: { item: RecentItem }) {
  const img = useRef<HTMLImageElement>(null);
  const cv = useRef<HTMLCanvasElement>(null);
  const [loaded, setLoaded] = useState(0);
  const [tick, setTick] = useState(0);
  useEffect(() => {
    if (!item.thumbUrl) return;
    const t = setInterval(() => setTick((n) => n + 1), 60000);
    return () => clearInterval(t);
  }, [item.thumbUrl]);
  const water = useRef<Water | null>(null);
  const shown = loaded > 0;
  // Create once per canvas; a thumbnail reload only re-uploads the image texture.
  useCanvasEffect(cv, (c) => {
    water.current = img.current ? createWater(c, { mode: "image", source: img.current }) : null;
    return water.current && { destroy: () => { water.current?.destroy(); water.current = null; } };
  }, [shown]);
  useEffect(() => { if (loaded > 0 && img.current) water.current?.setSource(img.current); }, [loaded]);
  return (
    <>
      {item.thumbUrl && (
        <img ref={img} src={`${item.thumbUrl}?t=${tick}`} alt="" draggable={false}
          className="absolute inset-0 size-full object-cover"
          onLoad={() => setLoaded((n) => n + 1)} onError={() => setLoaded(0)} />
      )}
      {shown && <canvas ref={cv} aria-hidden="true" />}
    </>
  );
}

function statusLine(r: RecentItem): string {
  if (r.kind === "desktop") return `Desktop, ${r.status === "connected" ? "connected now" : r.status}`;
  return `Container, ${statusMeta(r.status).label.toLowerCase()}`;
}

export function RecentStrip({ items, onAct }: { items: RecentItem[]; onAct: (r: RecentItem) => void }) {
  if (items.length === 0) return <p className="text-sm text-muted-foreground">Desktops and containers you open show up here.</p>;
  return (
    <ul className="grid grid-cols-[repeat(auto-fill,minmax(260px,1fr))] gap-[18px]">
      {items.map((r) => (
        <li key={r.id} className="grid gap-2" data-testid="recent">
          <div className="recent-shot aspect-[16/10] bg-secondary outline outline-1 -outline-offset-1 outline-border">
            <Shot item={r} />
            <GlassButton onClick={() => onAct(r)} aria-label={`${r.action} ${r.name}`}>{r.action}</GlassButton>
          </div>
          <strong className="font-semibold">{r.name}</strong>
          <span className="text-[13.5px] text-muted-foreground">{statusLine(r)}</span>
        </li>
      ))}
    </ul>
  );
}
