// Bayer-dithered "sun": soft glow rendered as an ordered 8x8 dot pattern. Port of login-waves.html sun().
const BAYER = [0,32,8,40,2,34,10,42, 48,16,56,24,50,18,58,26, 12,44,4,36,14,46,6,38, 60,28,52,20,62,30,54,22,
  3,35,11,43,1,33,9,41, 51,19,59,27,49,17,57,25, 15,47,7,39,13,45,5,37, 63,31,55,23,61,29,53,21];

const hash = (x: number, y: number, seed = 0) => {
  let h = (x * 374761393 + y * 668265263 + seed) ^ 0x5bd1e995;
  h = Math.imul(h ^ (h >>> 13), 1274126177);
  return ((h ^ (h >>> 16)) >>> 0) / 4294967296;
};

export const DITHER_CELL = 5, DITHER_DOT = 1.1, HORIZON_GAP = 18, HORIZON_FADE = 36;

/** Per-cell mask (1 = dot) at cell resolution, row-major over the full W*H grid of cells. Nothing at/below horizonY. */
export function ditherMask(W: number, H: number, dpr: number, horizonY: number, seed = 0): Uint8Array {
  const px = Math.round(DITHER_CELL * dpr), cols = Math.ceil(W / px), rows = Math.ceil(H / px);
  const m = new Uint8Array(cols * rows);
  const cx0 = W * 0.72, cy0 = H * 0.2, R = Math.max(W, H) * 0.55, B1 = px * 6, B2 = px * 14;
  for (let r = 0; r < rows; r++) {
    const y = r * px;
    if (y >= horizonY) break;
    for (let c = 0; c < cols; c++) {
      const X = c * px;
      const d = Math.hypot((X - cx0) * 0.85, (y - cy0) * 1.2) / R;
      if (d >= 1) continue;
      const fall = Math.pow(1 - d, 1.4) * Math.min(1, (horizonY - y) / (HORIZON_FADE * dpr));
      const n = 0.55 * hash((X / B1) | 0, (y / B1) | 0, seed) + 0.45 * hash(((X / B2) | 0) + 97, ((y / B2) | 0) + 31, seed);
      const v = fall * (n * 1.6 - 0.25);
      const th = (BAYER[(r % 8) * 8 + (c % 8)]! + 0.5) / 64;
      if (v > th) m[r * cols + c] = 1;
    }
  }
  return m;
}

const cache = new Map<string, HTMLCanvasElement>();

export function renderDitherSun(W: number, H: number, dpr: number, dark: boolean, horizonY: number): HTMLCanvasElement {
  const key = `${W}x${H}@${dpr}:${dark}:${Math.round(horizonY)}`;
  const hit = cache.get(key);
  if (hit) return hit;
  if (cache.size > 6) cache.clear();
  const c = document.createElement("canvas");
  c.width = W; c.height = H;
  const x = c.getContext("2d");
  if (x) {
    const px = Math.round(DITHER_CELL * dpr), cols = Math.ceil(W / px), m = ditherMask(W, H, dpr, horizonY);
    x.fillStyle = dark ? "rgba(170,222,224,.38)" : "rgba(30,96,102,.32)";
    for (let i = 0; i < m.length; i++) {
      if (!m[i]) continue;
      x.beginPath();
      x.arc((i % cols) * px + px / 2, Math.floor(i / cols) * px + px / 2, DITHER_DOT * dpr, 0, 6.283);
      x.fill();
    }
  }
  cache.set(key, c);
  return c;
}
