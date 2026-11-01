import { api, type Workstation } from "@/api/client";
import { statusMeta } from "@/lib/status";
import type { Instance } from "@/lib/types";

const KEY = "styxOpened";

export interface RecentItem {
  kind: "desktop" | "container";
  id: string;
  name: string;
  status: string;
  thumbUrl: string;
  action: "Resume" | "Connect" | "Start";
}

/** localStorage `styxOpened`: item id mapped to the ms timestamp of its last open. */
export function readOpened(): Record<string, number> {
  try {
    const v = JSON.parse(localStorage.getItem(KEY) ?? "{}");
    return v && typeof v === "object" ? v : {};
  } catch { return {}; }
}

export const OPENED_EVENT = "styx-opened";

export function recordOpened(id: string): void {
  try { localStorage.setItem(KEY, JSON.stringify({ ...readOpened(), [id]: Date.now() })); } catch { /* storage blocked */ }
  window.dispatchEvent(new Event(OPENED_EVENT));
}

/** The last `n` things opened, newest first; a desktop you are connected to right now always leads. Offline desktops are skipped. */
export function recentItems(instances: Instance[], workstations: Workstation[], opened: Record<string, number>, n = 3): RecentItem[] {
  const rows: { item: RecentItem; at: number; live: boolean }[] = [];
  for (const w of workstations) {
    if (w.status !== "online" || !(w.in_use_self || opened[w.id])) continue;
    rows.push({
      at: opened[w.id] ?? 0, live: w.in_use_self,
      item: {
        kind: "desktop", id: w.id, name: w.name, thumbUrl: api.workstationThumbUrl(w.id),
        status: w.in_use_self ? "connected" : w.in_use ? "in use" : "online",
        action: w.in_use_self ? "Resume" : "Connect",
      },
    });
  }
  for (const i of instances) {
    if (!opened[i.id]) continue;
    const g = statusMeta(i.status).group;
    rows.push({
      at: opened[i.id]!, live: false,
      item: {
        kind: "container", id: i.id, name: i.name, status: i.status,
        thumbUrl: g === "running" ? api.screenshotUrl(i.id) : "",
        action: g === "running" || g === "paused" ? "Resume" : "Start",
      },
    });
  }
  rows.sort((a, b) => Number(b.live) - Number(a.live) || b.at - a.at);
  return rows.slice(0, n).map((r) => r.item);
}
