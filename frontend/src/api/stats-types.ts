// Stats and TURN-check response types (split out of client.ts to keep it under 500 lines).
export type Tri = "ok" | "warn" | "fail";
export type StatTile = { now: number | null; series: (number | null)[] };
export type OverviewStats = {
  tiles: { cpu: StatTile; ram: StatTile; disk: StatTile; live: StatTile };
  health_hours: (Tri | null)[];
  load: { labels: string[]; cpu: (number | null)[]; ram: (number | null)[] };
  sessions_per_day: { date: string; count: number }[];
};
export type StreamingStats = { rows: { workstation: string; sub?: string; parts: Record<string, number> }[] };
export type RelayStats = {
  used_gb: number; free_gb: number; projected_gb: number; est_usd: number; budget_usd: number; budget_gb: number | null; relayed_pct: number;
  daily: { date: string; gb: number }[]; monthly: { month: string; gb: number }[];
  by_user: { name: string; gb: number }[]; by_workstation: { name: string; gb: number }[];
  reasons: { reason: string; sessions: number }[];
};
export type TurnCheckStatus = "ok" | "warn" | "error" | "skip";
export type TurnCheckItem = { id: string; label: string; status: TurnCheckStatus; detail: string };
export type TurnCheck = { provider: string; checked_at: string; checks: TurnCheckItem[] };
