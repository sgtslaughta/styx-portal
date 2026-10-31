/** Chart/sparkline series colors. Reference CSS vars from globals.css so they follow the theme. */
export const CHART_PALETTE = [
  "var(--chart-1)",
  "var(--chart-2)",
  "var(--chart-3)",
  "var(--chart-4)",
] as const;

export const CHART_COLORS = {
  cpu: "var(--chart-1)",
  memory: "var(--chart-2)",
  network: "var(--chart-3)",
  storage: "var(--chart-4)",
} as const;

export type Pt = readonly [number, number];

/** Smooth monotone cubic (Fritsch-Carlson) SVG path through points sorted by x. */
export function monotonePath(pts: readonly Pt[]): string {
  const n = pts.length;
  if (n === 0) return "";
  const f = (v: number) => v.toFixed(2);
  if (n === 1) return `M${f(pts[0]![0])},${f(pts[0]![1])}`;
  const dx: number[] = [], m: number[] = [];
  for (let i = 0; i < n - 1; i++) {
    dx.push(pts[i + 1]![0] - pts[i]![0]);
    m.push((pts[i + 1]![1] - pts[i]![1]) / (dx[i] || 1));
  }
  const t: number[] = [m[0]!];
  for (let i = 1; i < n - 1; i++) t.push(m[i - 1]! * m[i]! <= 0 ? 0 : (m[i - 1]! + m[i]!) / 2);
  t.push(m[n - 2]!);
  for (let i = 0; i < n - 1; i++) {
    if (m[i] === 0) { t[i] = 0; t[i + 1] = 0; continue; }
    const a = t[i]! / m[i]!, b = t[i + 1]! / m[i]!, s = a * a + b * b;
    if (s > 9) { const k = 3 / Math.sqrt(s); t[i] = k * a * m[i]!; t[i + 1] = k * b * m[i]!; }
  }
  let d = `M${f(pts[0]![0])},${f(pts[0]![1])}`;
  for (let i = 0; i < n - 1; i++) {
    const [x0, y0] = pts[i]!, [x1, y1] = pts[i + 1]!, h = dx[i]! / 3;
    d += `C${f(x0 + h)},${f(y0 + t[i]! * h)} ${f(x1 - h)},${f(y1 - t[i + 1]! * h)} ${f(x1)},${f(y1)}`;
  }
  return d;
}
