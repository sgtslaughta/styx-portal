/** Thumbnail capture for the /desktop wrapper: snapshots the same-origin Selkies frame and PUTs it. */
export const MAX_THUMB_W = 480;
export const THUMB_INTERVAL_MS = 45_000;
export const FIRST_THUMB_MS = 5_000;

/** Scale to at most MAX_THUMB_W wide, keeping aspect, never upscaling. */
export function scaleDims(w: number, h: number): { w: number; h: number } | null {
  if (!(w > 0) || !(h > 0)) return null;
  const k = Math.min(1, MAX_THUMB_W / w);
  return { w: Math.round(w * k), h: Math.max(1, Math.round(h * k)) };
}

/** Largest visible <video>/<canvas> (the Selkies output). */
export function pickMedia(doc: Document): HTMLVideoElement | HTMLCanvasElement | null {
  let best: Element | null = null;
  let area = 0;
  for (const e of Array.from(doc.querySelectorAll("video, canvas"))) {
    const r = e.getBoundingClientRect();
    if (r.width * r.height > area) { area = r.width * r.height; best = e; }
  }
  return best as HTMLVideoElement | HTMLCanvasElement | null;
}

function toBlob(c: HTMLCanvasElement, type: string, q: number): Promise<Blob | null> {
  return new Promise((res) => c.toBlob(res, type, q));
}

/** Draw the media into a small canvas and encode (webp, falling back to jpeg). Null on any problem. */
export async function captureThumb(doc: Document): Promise<Blob | null> {
  try {
    const m = pickMedia(doc);
    if (!m) return null;
    const sw = m instanceof HTMLVideoElement ? m.videoWidth : m.width;
    const sh = m instanceof HTMLVideoElement ? m.videoHeight : m.height;
    const d = scaleDims(sw, sh);
    if (!d) return null;
    const c = document.createElement("canvas");
    c.width = d.w; c.height = d.h;
    c.getContext("2d")?.drawImage(m, 0, 0, d.w, d.h);
    const webp = await toBlob(c, "image/webp", 0.7); // tainted canvas throws -> caught below
    if (webp && webp.type === "image/webp") return webp;
    return await toBlob(c, "image/jpeg", 0.7);
  } catch {
    return null;
  }
}

function csrf(): string | null {
  const m = document.cookie.match(/(?:^|; )csrf_token=([^;]*)/);
  return m?.[1] ? decodeURIComponent(m[1]) : null;
}

export async function uploadThumb(instanceId: string, blob: Blob): Promise<void> {
  const token = csrf();
  await fetch(`/api/instances/${instanceId}/screenshot`, {
    method: "PUT",
    credentials: "same-origin",
    headers: { "Content-Type": blob.type, "X-Styx-Client": "1", ...(token ? { "X-CSRF-Token": token } : {}) },
    body: blob,
  });
}

/** Start the periodic uploader; returns a stop function. Never throws, never touches the stream. */
export function startThumbUploader(instanceId: string, frame: () => HTMLIFrameElement | null): () => void {
  const tick = async () => {
    try {
      if (document.visibilityState !== "visible") return;
      const doc = frame()?.contentDocument;
      if (!doc) return;
      const blob = await captureThumb(doc);
      if (blob) await uploadThumb(instanceId, blob);
    } catch { /* thumbnails are best effort */ }
  };
  // First shot ~5 s after the stream first renders (poll for the media element).
  let first = 0;
  const poll = window.setInterval(() => {
    try {
      const doc = frame()?.contentDocument;
      if (doc && pickMedia(doc)) {
        window.clearInterval(poll);
        first = window.setTimeout(() => void tick(), FIRST_THUMB_MS);
      }
    } catch { /* cross-origin or detached: keep polling */ }
  }, 1000);
  const every = window.setInterval(() => void tick(), THUMB_INTERVAL_MS);
  return () => { window.clearInterval(poll); window.clearTimeout(first); window.clearInterval(every); };
}
