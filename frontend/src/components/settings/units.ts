/** Display units for settings stored in raw units (seconds etc). Per-key table. */
const UNITS: Record<string, { div: number; unit: string }> = {
  LOCKOUT_DURATION: { div: 60, unit: "min" },
  BAN_FAIL_WINDOW: { div: 60, unit: "min" },
  BAN_DURATION: { div: 3600, unit: "hours" },
  ACCESS_TTL: { div: 60, unit: "min" },
  REFRESH_TTL: { div: 86400, unit: "days" },
  MATRIX_SESSION_MAX_HOURS: { div: 1, unit: "hours" },
  WORKSTATION_IDLE_TIMEOUT_S: { div: 60, unit: "min" },
  WORKSTATION_IDLE_WARN_LEAD_S: { div: 1, unit: "sec" },
  WORKSTATION_OFFLINE_AFTER_S: { div: 1, unit: "sec" },
  WEBRTC_MAX_SESSION_H: { div: 1, unit: "hours" },
  WORKSTATION_SEAT_WIDTH: { div: 1, unit: "px" },
  WORKSTATION_SEAT_HEIGHT: { div: 1, unit: "px" },
  TURN_FREE_GB_MONTH: { div: 1, unit: "GB" },
  TURN_BUDGET_GB: { div: 1, unit: "GB" },
};

const PERIOD: Record<number, string> = { 1: "per sec", 60: "per min", 3600: "per hour", 86400: "per day" };

export function divisor(key: string): number {
  return UNITS[key]?.div ?? 1;
}

export function unitOf(key: string): string {
  return UNITS[key]?.unit ?? "";
}

/** Strip a trailing "(s)" / "(h)" / "(px)" from a label once the unit is shown beside the input. */
export function cleanLabel(key: string, label: string): string {
  return key in UNITS ? label.replace(/\s*\((s|h|px)\)$/, "") : label;
}

export function parseRate(raw: unknown): { n: number; s: number } | null {
  const m = /^(\d+)\/(\d+)$/.exec(String(raw ?? ""));
  return m ? { n: Number(m[1]), s: Number(m[2]) } : null;
}

export function toDisplay(key: string, raw: unknown): { value: number; unit: string } {
  const r = parseRate(raw);
  if (r) return { value: r.n, unit: PERIOD[r.s] ?? `per ${r.s}s` };
  const u = UNITS[key];
  return { value: Number(raw) / (u?.div ?? 1), unit: u?.unit ?? "" };
}

export function fromDisplay(key: string, value: number): number {
  return Math.round(value * divisor(key));
}
