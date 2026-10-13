import { useLayoutEffect, useState } from "react";
import type { ServiceTile } from "@/api/client";
import { frameAncestorsBlock, isFrameBlocked, isFrameLocationForbidden, shellPathFor } from "./url";

const POLL_MS = 500;
const POLL_MAX_MS = 10_000;

type Patched = { cw: Window; doc: Document; restore: () => void };

/** Mirrors the framed app's URL/title into the address bar. Returns true when the first load was refused. */
export function useFrameSync(
  frame: HTMLIFrameElement | null, tile: ServiceTile,
  onLeave: (href: string) => void, onTitle: (t: string) => void,
): boolean {
  const [blocked, setBlocked] = useState(false);
  useLayoutEffect(() => {
    if (!frame) return;
    let first = true;
    let patched: Patched | null = null;
    let observer: MutationObserver | null = null;
    const attach = () => {
      patched = null; // old document is gone; never touch its wrappers
      observer?.disconnect();
      observer = null;
      const wasFirst = first;
      first = false;
      if (isFrameBlocked(frame)) { if (wasFirst) setBlocked(true); return; }
      const cw = frame.contentWindow!;
      const doc = cw.document;
      const readTitle = () => { try { if (cw.document === doc) onTitle(doc.title); } catch { /* gone */ } };
      const sync = () => {
        try {
          const p = shellPathFor(tile.mount_mode, tile.slug, cw.location);
          if (p) window.history.replaceState(null, "", p); else onLeave(cw.location.href);
        } catch { return; }
        requestAnimationFrame(readTitle);
      };
      const { pushState, replaceState } = cw.history;
      cw.history.pushState = function (...a: Parameters<History["pushState"]>) { pushState.apply(this, a); sync(); };
      cw.history.replaceState = function (...a: Parameters<History["replaceState"]>) { replaceState.apply(this, a); sync(); };
      cw.addEventListener("popstate", sync);
      cw.addEventListener("hashchange", sync);
      const titleEl = doc.querySelector("title");
      const mo = titleEl && typeof MutationObserver !== "undefined" ? new MutationObserver(readTitle) : null;
      if (titleEl) mo?.observe(titleEl, { childList: true, characterData: true, subtree: true });
      observer = mo;
      patched = {
        cw, doc,
        restore: () => {
          mo?.disconnect();
          cw.history.pushState = pushState; cw.history.replaceState = replaceState;
          cw.removeEventListener("popstate", sync); cw.removeEventListener("hashchange", sync);
        },
      };
      sync();
    };
    // Chromium fires no load event for a frame refused by CSP frame-ancestors; its error page is cross-origin.
    const started = Date.now();
    // In some builds the refused frame just stays about:blank (same-origin): ask the app's own headers once.
    let ticks = 0;
    const abort = new AbortController();
    const block = () => { first = false; window.clearInterval(poll); setBlocked(true); };
    const probe = () => {
      const src = frame.getAttribute("src");
      if (!src) return;
      fetch(src, { credentials: "same-origin", signal: abort.signal }).then((r) => {
        void r.body?.cancel();
        if (first && frameAncestorsBlock(r.headers.get("content-security-policy"))) block();
      }).catch(() => { /* offline or refused: the load event path still applies */ });
    };
    const poll = window.setInterval(() => {
      if (!first || Date.now() - started > POLL_MAX_MS) { window.clearInterval(poll); return; }
      if (isFrameLocationForbidden(frame)) block();
      else if (++ticks === 2) probe();
    }, POLL_MS);
    const onLoad = () => { window.clearInterval(poll); attach(); };
    frame.addEventListener("load", onLoad);
    return () => {
      abort.abort();
      window.clearInterval(poll);
      frame.removeEventListener("load", onLoad);
      const p = patched as Patched | null;
      try { if (p && p.cw.document === p.doc) p.restore(); } catch { /* frame gone */ }
    };
    // Keyed on slug/mode, not tile identity: a refetch returning an equal tile must not re-attach.
  }, [frame, tile.slug, tile.mount_mode, onLeave, onTitle]);
  return blocked;
}
