import { useEffect, useRef, useState } from "react";

/** Measured size of an element (falls back to defaults where layout is unavailable, e.g. jsdom). */
export function useSize<T extends HTMLElement>(dw = 320, dh = 170) {
  const ref = useRef<T>(null);
  const [size, setSize] = useState({ w: dw, h: dh });
  useEffect(() => {
    const el = ref.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    const read = () => {
      const w = el.clientWidth, h = el.clientHeight;
      if (w > 0 && h > 0) setSize((s) => (s.w === w && s.h === h ? s : { w, h }));
    };
    read();
    const ro = new ResizeObserver(read);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  return [ref, size] as const;
}
