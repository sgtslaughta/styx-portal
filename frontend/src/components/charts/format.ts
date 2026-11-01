export const fmtPct = (v: number) => `${Math.round(v)}%`;
export const fmtGb = (v: number) => `${v >= 100 ? Math.round(v).toLocaleString("en-US") : +v.toFixed(1)} GB`;
export const fmtUsd = (v: number) => `$${v.toFixed(2)}`;
export const fmtHours = (v: number) => `${+v.toFixed(1)} h`;
/** "2026-11-01" -> "1 Nov" (parsed at noon so the local timezone cannot shift the day). */
export const shortDate = (iso: string) => new Date(`${iso}T12:00:00`).toLocaleDateString("en-US", { month: "short", day: "numeric" });
/** "2026-11" -> "Nov" */
export const shortMonth = (ym: string) => new Date(`${ym}-15T12:00:00`).toLocaleDateString("en-US", { month: "short" });
