import type { Workstation } from "@/api/client";

export type Field = "transport" | "encoder" | "framerate" | "bitrate_kbps";
/** wsId -> field -> staged value ("" = inherit the default). */
export type WsEdits = Record<string, Partial<Record<Field, string>>>;

export const DEFAULT_ENCODER = "auto";
export const DEFAULT_FPS = 60;
export const CODECS: readonly (readonly [string, string])[] = [["av1", "AV1"], ["hevc", "HEVC"], ["h264", "H.264"]];
export const CODEC_LABEL: Record<string, string> = { auto: "Auto", av1: "AV1", hevc: "HEVC", h264: "H.264" };
export const TRANSPORT_LABEL: Record<string, string> = { websockets: "WebSockets", webrtc: "WebRTC" };

/** Saved value as a string; "" = inherited. Encoder auto and 60 fps are the defaults, so they count as inherited. */
export function saved(ws: Workstation, f: Field): string {
  const v = ws.stream_settings?.[f];
  if (v == null || v === "") return "";
  if (f === "encoder" && v === DEFAULT_ENCODER) return "";
  if (f === "framerate" && Number(v) === DEFAULT_FPS) return "";
  if (f === "transport" && v !== "websockets" && v !== "webrtc") return "";
  return String(v);
}

export const current = (ws: Workstation, edits: WsEdits, f: Field) => edits[ws.id]?.[f] ?? saved(ws, f);

export function setField(edits: WsEdits, ws: Workstation, f: Field, v: string): WsEdits {
  const mine = { ...edits[ws.id] };
  if (v === saved(ws, f)) delete mine[f]; else mine[f] = v;
  const next = { ...edits };
  if (Object.keys(mine).length) next[ws.id] = mine; else delete next[ws.id];
  return next;
}

export const editCount = (edits: WsEdits) => Object.values(edits).reduce((n, m) => n + Object.keys(m).length, 0);

/** stream_settings payload for one workstation: saved settings with staged edits applied. */
export function mergedSettings(ws: Workstation, mine: Partial<Record<Field, string>>): Record<string, unknown> {
  const next: Record<string, unknown> = { ...ws.stream_settings };
  for (const [f, v] of Object.entries(mine) as [Field, string][]) {
    if (v === "") delete next[f];
    else next[f] = f === "framerate" || f === "bitrate_kbps" ? Number(v) : v;
  }
  return next;
}
