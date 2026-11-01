// Dim monospace glyph grid with soft diagonal light beams. Port of login-waves.html glyph IIFE.
import { isDark, runLoop, type Effect } from "./types";

export const BEAM_PERIOD = 230, BEAM_WIDTH = 34, BEAM_SPEED = 85;
const CH = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz0123456789<>[]{}/\\|=+-*#%&$@?!:;~^ΣΤΥΞΩΔΛΦΨ";
const pick = () => CH[(Math.random() * CH.length) | 0]!;

export const bell = (v: number, w: number) => Math.exp(-(v * v) / (2 * w * w));
export const wrap = (v: number, p: number) => ((v % p) + p) % p;

/** Narrow-beam intensity (0..1) at pixel (x,y), time t seconds; beams run along the 45deg axis, period 230px*dpr. */
export function beamIntensity(x: number, y: number, t: number, dpr = 1): number {
  const u = (x + y) * Math.SQRT1_2, period = BEAM_PERIOD * dpr;
  return bell(wrap(u - t * BEAM_SPEED * dpr, period) - period / 2, BEAM_WIDTH * dpr);
}

/** 0 inside the ellipse (calm), ramping to 1 outside. */
export function calmFactor(x: number, y: number, r: { cx: number; cy: number; rx: number; ry: number }, inner: number, k: number) {
  return Math.min(1, Math.max(0, Math.hypot((x - r.cx) / r.rx, (y - r.cy) / r.ry) - inner) * k);
}

export function createGlyphBeams(canvas: HTMLCanvasElement, opts: { calmRects: () => DOMRect[] }): Effect {
  const g = canvas.getContext("2d");
  if (!g) return { destroy() {} };
  const host = canvas.parentElement ?? canvas;
  const reduce = window.matchMedia?.("(prefers-reduced-motion: reduce)");
  let W = 0, H = 0, dpr = 1, cols = 0, rows = 0, cell = 19, grid: string[] = [], phase = new Float32Array(0);

  function onSize(w: number, h: number, d: number) {
    W = w; H = h; dpr = d; cell = 19 * d; cols = Math.ceil(W / cell); rows = Math.ceil(H / cell);
    grid = Array.from({ length: cols * rows }, pick);
    phase = Float32Array.from({ length: cols * rows }, () => Math.random() * 6.283);
  }
  function draw(ms: number) {
    const t = reduce?.matches ? 4 : ms / 1000, dark = isDark();
    g!.clearRect(0, 0, W, H);
    g!.font = `${12 * dpr}px "IBM Plex Mono", monospace`; g!.textAlign = "center"; g!.textBaseline = "middle";
    const fr = host.getBoundingClientRect();
    const [card, logo] = opts.calmRects();
    const ell = (r: DOMRect | undefined, sx: number, sy: number, ax: number, ay: number) => r
      ? { cx: (r.left - fr.left + r.width / 2) * dpr, cy: (r.top - fr.top + r.height / 2) * dpr, rx: (r.width * sx + ax) * dpr, ry: (r.height * sy + ay) * dpr } : null;
    const ce = ell(card, 0.95, 1.05, 0, 0), le = ell(logo, 0.8, 1, 24, 26);
    for (let r = 0; r < rows; r++) for (let c = 0; c < cols; c++) {
      const x = (c + 0.5) * cell, y = (r + 0.5) * cell, i = r * cols + c;
      const b1 = beamIntensity(x, y, t, dpr);
      const u = (x + y) * Math.SQRT1_2;
      const b2 = 0.35 * bell(wrap(u - t * 30 * dpr, BEAM_PERIOD * dpr * 3.2) - BEAM_PERIOD * dpr * 1.6, BEAM_WIDTH * dpr * 4);
      const shimmer = 0.65 + 0.35 * Math.sin(t * 9 + phase[i]!);
      const beam = Math.min(1, b1 * shimmer + b2);
      const calm0 = ce ? calmFactor(x, y, ce, 0.62, 1.5) : 1;
      const calm = calm0 * (le ? calmFactor(x, y, le, 0.7, 1.6) : 1);
      const edge = Math.min(1, x / (60 * dpr), (W - x) / (60 * dpr), y / (60 * dpr), (H - y) / (60 * dpr));
      const a = (0.06 + beam * 0.6) * calm * edge;
      if (a < 0.02) continue;
      if (!reduce?.matches && Math.random() < b1 * 0.18) grid[i] = pick();
      const w = beam * beam;
      g!.fillStyle = dark
        ? `rgba(${(111 + 130 * w) | 0},${(183 + 35 * w) | 0},${(188 - 30 * w) | 0},${a})`
        : `rgba(${(42 + 100 * w) | 0},${(118 - 10 * w) | 0},${(124 - 80 * w) | 0},${a * 1.1})`;
      g!.fillText(grid[i]!, x, y);
    }
  }
  return runLoop(host, canvas, { onSize, draw, minDelta: 33 });
}
