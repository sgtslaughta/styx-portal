import type { Workstation } from "@/api/client";
import type { Instance } from "@/lib/types";
import { readLocal, writeLocal } from "@/lib/local";
import { isRunning, statusMeta } from "@/lib/status";
import { formatDuration, shortError } from "@/lib/utils";

export type WorkspaceKind = "workstation" | "instance";
export type Selection = { kind: WorkspaceKind; id: string };

const RECENT_KEY = "styx.home.recent";

/** The workspace last opened (Connect/Open) in this browser, or null. */
export function readRecent(): Selection | null {
  try {
    const v = JSON.parse(readLocal(RECENT_KEY) ?? "null") as Partial<Selection> | null;
    if (v && (v.kind === "workstation" || v.kind === "instance") && typeof v.id === "string") return { kind: v.kind, id: v.id };
  } catch { /* garbage: no recent */ }
  return null;
}

export function writeRecent(s: Selection): void {
  writeLocal(RECENT_KEY, JSON.stringify(s));
}

/** Compact age: "4s", "5m", "3h", "1 day", "2 days". Null or unparsable input -> null. */
export function since(iso: string | null, now = Date.now()): string | null {
  if (!iso) return null;
  const t = new Date(iso).getTime();
  if (Number.isNaN(t)) return null;
  const s = Math.max(0, Math.floor((now - t) / 1000));
  if (s < 60) return `${s}s`;
  if (s < 3600) return `${Math.floor(s / 60)}m`;
  if (s < 86_400) return `${Math.floor(s / 3600)}h`;
  const d = Math.floor(s / 86_400);
  return `${d} day${d === 1 ? "" : "s"}`;
}

/** Human OS name: pretty_name, else distro, else "Linux". */
export function osName(ws: Workstation): string {
  const { pretty_name, distro } = ws.os_info ?? {};
  if (typeof pretty_name === "string" && pretty_name) return pretty_name;
  if (typeof distro === "string" && distro) return distro;
  return "Linux";
}

/** One secondary line per workstation row. */
export function wsLine(ws: Workstation, now = Date.now()): string {
  const seen = since(ws.last_heartbeat, now);
  if (ws.status !== "online") return seen ? `Offline · ${seen}` : "Offline";
  if (ws.in_use && !ws.in_use_self) return `In use by ${ws.in_use_by ?? "someone"}`;
  if (ws.in_use_self) return "Connected (you)";
  const os = osName(ws);
  return seen ? `${os} · seen ${seen} ago` : os;
}

export function wsDot(ws: Workstation): { dotClass: string; label: string } {
  if (ws.status !== "online") return { dotClass: "bg-muted-foreground", label: "Offline" };
  if (ws.last_error) return { dotClass: "bg-destructive", label: "Error" };
  if (ws.in_use) return { dotClass: "bg-warning", label: ws.in_use_self ? "Connected (you)" : `In use by ${ws.in_use_by ?? "someone"}` };
  return { dotClass: "bg-success", label: "Online" };
}

/** One secondary line per instance row: "Running · up 6d 5h" | "Stopped" | "Error · <short reason>". */
export function instLine(inst: Instance, now = Date.now()): string {
  const label = statusMeta(inst.status).label;
  if (inst.started_at && isRunning(inst.status)) {
    return `${label} · up ${formatDuration((now - new Date(inst.started_at + "Z").getTime()) / 1000)}`;
  }
  if (inst.status === "error" && inst.error_message) return `Error · ${shortError(inst.error_message, 40)}`;
  return label;
}
