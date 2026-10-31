/** Browser-side activity heartbeat: tells the backend the user is really using the instance tab. */
import { api } from "@/api/client";
import { pickMedia } from "@/lib/stream-thumb";

export const INPUT_WINDOW_MS = 5 * 60_000;
export const MOTION_WINDOW_MS = 2 * 60_000;
export const BEAT_MS = 60_000;
export const SAMPLE_MS = 10_000;
const MOVE_THROTTLE_MS = 5_000;
const LUMA_THRESHOLD = 2;
const SW = 32;
const SH = 18;
const EVENTS = ["keydown", "pointerdown", "pointermove", "wheel", "touchstart"] as const;

export interface ActivityState { now: number; lastInput: number; lastMotion: number; visible: boolean }

/** Recent input, or on-screen video motion while the tab is visible. */
export function isActive(s: ActivityState): boolean {
  return s.now - s.lastInput < INPUT_WINDOW_MS || (s.visible && s.now - s.lastMotion < MOTION_WINDOW_MS);
}

/** Mean absolute luma difference (0-255) between two RGBA buffers; Infinity if sizes differ. */
export function frameDiff(a: Uint8ClampedArray, b: Uint8ClampedArray): number {
  if (a.length !== b.length || a.length === 0) return Infinity;
  const luma = (d: Uint8ClampedArray, i: number) => 0.299 * d[i]! + 0.587 * d[i + 1]! + 0.114 * d[i + 2]!;
  let sum = 0;
  for (let i = 0; i < a.length; i += 4) sum += Math.abs(luma(a, i) - luma(b, i));
  return sum / (a.length / 4);
}

export function hasMotion(a: Uint8ClampedArray, b: Uint8ClampedArray): boolean {
  return frameDiff(a, b) > LUMA_THRESHOLD;
}

// ponytail: audio-only playback (music, no picture) is NOT detected; add an AudioContext analyser if needed.
export function startActivityHeartbeat(instanceId: string, getFrame: () => HTMLIFrameElement | null): () => void {
  let lastInput = Date.now();
  let lastMotion = 0;
  let lastMove = 0;
  let prev: Uint8ClampedArray | null = null;
  const attached = new Set<Window>();
  const canvas = document.createElement("canvas");
  canvas.width = SW; canvas.height = SH;

  const onInput = (e: Event) => {
    const now = Date.now();
    if (e.type === "pointermove") {
      if (now - lastMove < MOVE_THROTTLE_MS) return;
      lastMove = now;
    }
    lastInput = now;
  };
  const attach = (w: Window | null | undefined) => {
    if (!w || attached.has(w)) return;
    try {
      for (const t of EVENTS) w.addEventListener(t, onInput, { passive: true, capture: true });
      attached.add(w);
    } catch { /* cross-origin */ }
  };
  const attachFrame = () => {
    try { attach(getFrame()?.contentWindow); } catch { /* cross-origin */ }
  };
  attach(window);
  attachFrame();
  const frame = getFrame();
  const onLoad = () => { attached.forEach((w) => { if (w !== window) attached.delete(w); }); attachFrame(); };
  frame?.addEventListener("load", onLoad);

  const sample = () => {
    try {
      if (document.visibilityState !== "visible") return;
      attachFrame();
      const doc = getFrame()?.contentDocument;
      const m = doc && pickMedia(doc);
      if (!m) return;
      const ctx = canvas.getContext("2d", { willReadFrequently: true });
      if (!ctx) return;
      ctx.drawImage(m, 0, 0, SW, SH);
      const cur = ctx.getImageData(0, 0, SW, SH).data;
      if (prev && hasMotion(prev, cur)) lastMotion = Date.now();
      prev = cur;
    } catch { prev = null; }
  };
  const beat = () => {
    const visible = document.visibilityState === "visible";
    if (isActive({ now: Date.now(), lastInput, lastMotion, visible })) api.keepalive(instanceId).catch(() => {});
  };
  const t1 = setInterval(sample, SAMPLE_MS);
  const t2 = setInterval(beat, BEAT_MS);
  return () => {
    clearInterval(t1); clearInterval(t2);
    frame?.removeEventListener("load", onLoad);
    attached.forEach((w) => { try { for (const t of EVENTS) w.removeEventListener(t, onInput, { capture: true }); } catch { /* gone */ } });
  };
}
