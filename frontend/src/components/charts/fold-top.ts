import type { Slot } from "./axis";

export type Others<T> = { label: "Others"; sub: string; others: T[] };

/** Keep the n largest rows; fold the rest into one "Others" row (never a new hue). */
export function foldTop<T>(rows: T[], n: number, value: (r: T) => number): (T | Others<T>)[] {
  const sorted = [...rows].sort((a, b) => value(b) - value(a));
  if (sorted.length <= n) return sorted;
  return [...sorted.slice(0, n), { label: "Others", sub: `${sorted.length - n} more`, others: sorted.slice(n) }];
}

const SLOTS: Slot[] = ["s1", "s2", "s3", "s4", "s5"];
const sum = (p: Record<string, number>) => Object.values(p).reduce((a, b) => a + b, 0);

/** Top-n names by total get s1..s5 (ties broken by name, so order never matters); the rest fold into Others (s0). */
export function foldSeries<R extends { parts: Record<string, number> }>(rows: R[], n = 5) {
  const totals: Record<string, number> = {};
  for (const r of rows) for (const [u, v] of Object.entries(r.parts)) totals[u] = (totals[u] ?? 0) + v;
  const names = Object.keys(totals).sort((a, b) => totals[b]! - totals[a]! || a.localeCompare(b));
  const top = names.slice(0, n);
  const series: { name: string; slot: Slot }[] = top.map((name, i) => ({ name, slot: SLOTS[i]! }));
  if (names.length > n) series.push({ name: "Others", slot: "s0" });
  const fold = (parts: Record<string, number>) => {
    const o: Record<string, number> = {};
    for (const [u, v] of Object.entries(parts)) { const k = top.includes(u) ? u : "Others"; o[k] = (o[k] ?? 0) + v; }
    return o;
  };
  return { series, rows: rows.map((r) => ({ ...r, parts: fold(r.parts) })) };
}

export type StreamRow = { workstation: string; sub?: string; parts: Record<string, number> };
export type StackRow = { label: string; sub?: string; parts: Record<string, number> };

/** Streaming time: top-n workstations (rest -> one "Others" row) split by top-n users (rest -> Others). */
export function foldStreaming(rows: StreamRow[], n = 5) {
  const { series } = foldSeries(rows, n);
  const names = new Set(series.map((s) => s.name));
  const fold = (parts: Record<string, number>) => {
    const o: Record<string, number> = {};
    for (const [u, v] of Object.entries(parts)) { const k = names.has(u) ? u : "Others"; o[k] = (o[k] ?? 0) + v; }
    return o;
  };
  const merged = foldTop(rows, n, (r) => sum(r.parts)).map((r): StackRow => {
    if ("others" in r) {
      const parts: Record<string, number> = {};
      for (const o of r.others) for (const [u, v] of Object.entries(o.parts)) parts[u] = (parts[u] ?? 0) + v;
      return { label: r.label, sub: r.sub, parts: fold(parts) };
    }
    return { label: r.workstation, sub: r.sub, parts: fold(r.parts) };
  });
  return { series, rows: merged };
}
