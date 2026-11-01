/** Chart geometry helpers shared by the SVG charts. */
export type Slot = "s0" | "s1" | "s2" | "s3" | "s4" | "s5";
export const slotVar = (s: Slot) => `var(--${s})`;
export const known = (v: number | null | undefined): v is number => typeof v === "number" && Number.isFinite(v);

/** Round a step up to the 1-2-5 sequence (1, 2, 5, 10, 20, 50 ...). */
function niceStep(raw: number): number {
  const p = 10 ** Math.floor(Math.log10(raw));
  const n = raw / p;
  return (n <= 1 ? 1 : n <= 2 ? 2 : n <= 5 ? 5 : 10) * p;
}

/** Ticks from 0 up to the first multiple of a 1-2-5 step at or above `max`. */
export function niceTicks(max: number, count = 4): number[] {
  if (!known(max) || max <= 0) return [0, 1];
  const step = niceStep(max / count);
  const out: number[] = [];
  for (let i = 0; i <= Math.ceil(max / step - 1e-9); i++) out.push(+(i * step).toPrecision(12));
  return out;
}

/** Split a series into runs of consecutive known values so lines break on null. */
export function runs(data: (number | null | undefined)[]): { i: number; v: number }[][] {
  const out: { i: number; v: number }[][] = [];
  let cur: { i: number; v: number }[] = [];
  data.forEach((v, i) => {
    if (known(v)) cur.push({ i, v });
    else if (cur.length) { out.push(cur); cur = []; }
  });
  if (cur.length) out.push(cur);
  return out;
}

/** SVG path for one run, using an x/y mapper. */
export const runPath = (r: { i: number; v: number }[], x: (i: number) => number, y: (v: number) => number) =>
  r.map((p, k) => `${k ? "L" : "M"}${x(p.i).toFixed(1)},${y(p.v).toFixed(1)}`).join("");
