export type Effect = { destroy(): void };

const isDark = () => document.documentElement.classList.contains("dark");
export { isDark };

/** Shared rAF/visibility/resize/theme driver. `draw(ms)` renders one frame. */
export function runLoop(
  host: Element,
  canvas: HTMLCanvasElement,
  opts: { onSize: (w: number, h: number, dpr: number) => void; draw: (ms: number) => void; minDelta?: number },
): Effect {
  const still = window.matchMedia?.("(prefers-reduced-motion: reduce)");
  let raf = 0, last = -1e9;
  const tick = (ms: number) => {
    raf = 0;
    if (ms - last >= (opts.minDelta ?? 0)) { last = ms; opts.draw(ms); }
    if (!still?.matches && !document.hidden) raf = requestAnimationFrame(tick);
  };
  const kick = () => { cancelAnimationFrame(raf); last = -1e9; raf = requestAnimationFrame(tick); };
  const resize = () => {
    const r = host.getBoundingClientRect(), dpr = window.devicePixelRatio || 1;
    canvas.width = Math.max(1, Math.round(r.width * dpr));
    canvas.height = Math.max(1, Math.round(r.height * dpr));
    opts.onSize(canvas.width, canvas.height, dpr);
    kick();
  };
  const ro = typeof ResizeObserver !== "undefined" ? new ResizeObserver(resize) : null;
  ro?.observe(host);
  if (!ro) resize();
  const mo = new MutationObserver(() => still?.matches && kick());
  mo.observe(document.documentElement, { attributes: true, attributeFilter: ["class"] });
  document.addEventListener("visibilitychange", kick);
  return {
    destroy() {
      cancelAnimationFrame(raf);
      ro?.disconnect();
      mo.disconnect();
      document.removeEventListener("visibilitychange", kick);
    },
  };
}
