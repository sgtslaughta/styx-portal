import { useEffect, useLayoutEffect, useRef, useState, type RefObject } from "react";
import { animate, m, useMotionValue, useReducedMotion } from "framer-motion";
import { spring } from "@/lib/motion";
import { clampY, markDragging, readPos, snapSide, writePos, type FerryPos } from "./ferry-pos";

const SIZE_X = 44;
const SIZE_Y = 56;
const target = (p: FerryPos) => ({
  x: p.side === "left" ? 0 : window.innerWidth - SIZE_X,
  y: Math.round(p.y * window.innerHeight - SIZE_Y / 2),
});

/** The draggable handle on the viewport edge. Snaps to left/right and remembers where it was left. */
export function EdgeTab({ onOpen, open = false, tabRef }:
  { onOpen: () => void; open?: boolean; tabRef?: RefObject<HTMLButtonElement | null> }) {
  const reduce = useReducedMotion();
  const [pos, setPos] = useState(readPos);
  const [idle, setIdle] = useState(false);
  const bounds = useRef<HTMLDivElement>(null);
  const dragged = useRef(false);
  const timer = useRef<number>(undefined);
  const x = useMotionValue(0);
  const y = useMotionValue(0);

  const wake = () => {
    setIdle(false);
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => setIdle(true), 3000);
  };
  useEffect(() => { wake(); return () => window.clearTimeout(timer.current); }, []);
  useLayoutEffect(() => {
    const place = () => { const t = target(pos); x.set(t.x); y.set(t.y); };
    place();
    window.addEventListener("resize", place);
    return () => window.removeEventListener("resize", place);
  }, [pos, x, y]);

  const left = pos.side === "left";
  return (
    <>
      <div ref={bounds} aria-hidden className="pointer-events-none fixed inset-0" />
      <m.button
        ref={tabRef} type="button" aria-haspopup="dialog" aria-expanded={open}
        aria-label="Open the Styx menu (Alt+Shift+S)"
        drag dragConstraints={bounds} dragElastic={0.1} dragMomentum={false}
        style={{ x, y, width: SIZE_X, height: SIZE_Y }}
        animate={{ opacity: idle ? 0.35 : 1 }}
        onPointerEnter={wake} onFocus={wake} onTouchStart={wake}
        onPointerDown={() => {
          dragged.current = false; wake();
          // Arm at press, not at drag start: the first moves can already be over the app frame.
          markDragging(true);
          const release = () => { markDragging(false); window.removeEventListener("pointerup", release); window.removeEventListener("pointercancel", release); };
          window.addEventListener("pointerup", release);
          window.addEventListener("pointercancel", release);
        }}
        onDragStart={() => { dragged.current = true; }}
        onDragEnd={(_, info) => {
          markDragging(false);
          const next: FerryPos = { side: snapSide(info.point.x, window.innerWidth), y: clampY(info.point.y / window.innerHeight) };
          writePos(next);
          setPos(next);
          const t = target(next);
          if (reduce) { x.set(t.x); y.set(t.y); return; }
          void animate(x, t.x, spring);
          void animate(y, t.y, spring);
        }}
        onClick={() => { if (!dragged.current) onOpen(); dragged.current = false; }}
        className={`fixed left-0 top-0 z-40 flex cursor-grab touch-none items-center bg-transparent outline-none active:cursor-grabbing focus-visible:ring-2 focus-visible:ring-ring ${left ? "justify-start rounded-r-md" : "justify-end rounded-l-md"}`}
      >
        <span className={`flex h-14 w-2.5 items-center justify-center bg-primary ${left ? "rounded-r-full" : "rounded-l-full"}`}>
          <span className="h-6 w-px bg-[#EDF1EF]/20" />
        </span>
      </m.button>
    </>
  );
}
