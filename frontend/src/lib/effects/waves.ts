// Gold wave field in perspective with a Bayer-dithered sun. Port of login-waves.html (no cursor interaction).
import { isDark, runLoop, type Effect } from "./types";
import { HORIZON_GAP, renderDitherSun } from "./dither-sun";

export type { Effect };
export interface WavesOptions { lines?: number; top?: number; calmRect?: () => DOMRect | null }

const wave = (x: number, i: number, t: number) =>
  Math.sin(x * 2.1 + i * 0.37 + t * 0.55) * 0.55 + Math.sin(x * 4.3 - i * 0.21 + t * 0.9) * 0.28 +
  Math.sin(x * 7.7 + i * 0.83 - t * 0.4) * 0.12 + Math.sin(x * 1.3 - i * 0.11 + t * 0.25) * 0.4;

const METAL = ["#8A6420", "#D6AE58", "#F6E2A8", "#B88A35", "#EED08A", "#9C7228", "#E3C070", "#FBEBC0", "#A97C2E"];

export function createWaves(canvas: HTMLCanvasElement, opts: WavesOptions = {}): Effect {
  const cx = canvas.getContext("2d");
  if (!cx) return { destroy() {} };
  const N = opts.lines ?? 28, topF = opts.top ?? 0.42, steps = 90;
  const still = window.matchMedia?.("(prefers-reduced-motion: reduce)");
  let W = 0, H = 0, dpr = 1;
  const host = canvas.parentElement ?? canvas;

  function draw(ms: number) {
    const t = still?.matches ? 0 : ms / 1000, dark = isDark();
    const bg = cx!.createLinearGradient(0, H, W, 0);
    bg.addColorStop(0, dark ? "#0B171C" : "#E9EEEC"); bg.addColorStop(1, dark ? "#16323A" : "#A9C9CA");
    cx!.fillStyle = bg; cx!.fillRect(0, 0, W, H);
    const glow = cx!.createRadialGradient(W * 0.8, H * 0.15, 0, W * 0.8, H * 0.15, W * 0.6);
    glow.addColorStop(0, dark ? "rgba(111,183,188,.16)" : "rgba(42,118,124,.2)"); glow.addColorStop(1, "transparent");
    cx!.fillStyle = glow; cx!.fillRect(0, 0, W, H);
    cx!.drawImage(renderDitherSun(W, H, dpr, dark, H * topF - HORIZON_GAP * dpr), 0, 0);

    const top = H * topF;
    const metal = cx!.createLinearGradient(0, 0, W, 0);
    METAL.forEach((c, k, a) => metal.addColorStop(k / (a.length - 1), c));
    const sx = (((t * 0.03 + 0.55) % 1.6) - 0.3) * W, spec = cx!.createLinearGradient(sx - W * 0.5, 0, sx + W * 0.5, 0);
    if (dark) { spec.addColorStop(0, "rgba(255,236,190,.6)"); spec.addColorStop(0.5, "rgba(255,250,232,1)"); spec.addColorStop(1, "rgba(255,236,190,.6)"); }
    else { spec.addColorStop(0, "rgba(110,76,22,.55)"); spec.addColorStop(0.5, "rgba(70,46,10,.95)"); spec.addColorStop(1, "rgba(110,76,22,.55)"); }
    for (let i = 0; i < N; i++) {
      const d = i / (N - 1), y0 = top + (H - top) * Math.pow(d, 1.6);
      const amp = (10 + 46 * d) * dpr, lw = (0.7 + 1.5 * d) * dpr;
      const alpha = 0.45 + (dark ? 0.55 : 0.5) * Math.pow(d, 0.8);
      const pts: number[] = [], P = (k: number) => pts[k]!;
      for (let s = 0; s <= steps; s++) { const u = s / steps; pts.push(u * W, y0 + wave(u, i, t) * amp); }
      const path = (off: number) => {
        cx!.beginPath(); cx!.moveTo(P(0) + off, P(1) + off);
        for (let k = 2; k < pts.length - 2; k += 2)
          cx!.quadraticCurveTo(P(k) + off, P(k + 1) + off, (P(k) + P(k + 2)) / 2 + off, (P(k + 1) + P(k + 3)) / 2 + off);
        cx!.lineTo(P(pts.length - 2) + off, P(pts.length - 1) + off);
      };
      cx!.globalAlpha = alpha * (dark ? 0.6 : 0.75); cx!.strokeStyle = dark ? "#000" : "rgba(45,30,8,.85)"; cx!.lineWidth = lw; path(lw * 0.8); cx!.stroke();
      cx!.globalAlpha = alpha; cx!.strokeStyle = metal; path(0); cx!.stroke();
      cx!.globalCompositeOperation = dark ? "lighter" : "source-over"; cx!.globalAlpha = Math.min(1, alpha * 1.1);
      cx!.strokeStyle = spec; cx!.lineWidth = lw * 0.45; path(-lw * 0.3); cx!.stroke(); cx!.globalCompositeOperation = "source-over";
    }
    cx!.globalAlpha = 1;
    // Calm water behind the headline.
    const hero = opts.calmRect?.(), br = host.getBoundingClientRect();
    if (hero) {
      const hx = (hero.left - br.left + hero.width * 0.4) * dpr, hy = (hero.top - br.top + hero.height * 0.5) * dpr;
      const calm = cx!.createRadialGradient(hx, hy, 0, hx, hy, Math.max(hero.width, 420) * 0.85 * dpr);
      const base = dark ? "11,23,28" : "226,234,232";
      calm.addColorStop(0, `rgba(${base},.92)`); calm.addColorStop(0.55, `rgba(${base},.7)`); calm.addColorStop(1, `rgba(${base},0)`);
      cx!.save(); cx!.scale(1, 0.55); cx!.translate(0, hy / 0.55 - hy); cx!.fillStyle = calm; cx!.fillRect(0, 0, W, H / 0.55); cx!.restore();
    }
  }
  return runLoop(host, canvas, { onSize: (w, h, d) => { W = w; H = h; dpr = d; }, draw });
}
