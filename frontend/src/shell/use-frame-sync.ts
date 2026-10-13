import { useEffect, useState, type RefObject } from "react";
import type { ServiceTile } from "@/api/client";
import { isFrameBlocked, shellPathFor } from "./url";

/** Mirrors the framed app's URL/title into the address bar. Returns true when the frame refused to load. */
export function useFrameSync(
  ref: RefObject<HTMLIFrameElement | null>, tile: ServiceTile,
  onLeave: (href: string) => void, onTitle: (t: string) => void,
): boolean {
  const [blocked, setBlocked] = useState(false);
  useEffect(() => {
    const frame = ref.current;
    if (!frame) return;
    let detach = () => {};
    const attach = () => {
      detach();
      if (isFrameBlocked(frame)) { setBlocked(true); return; }
      const cw = frame.contentWindow!;
      const sync = () => {
        try {
          const p = shellPathFor(tile.mount_mode, tile.slug, cw.location);
          if (p) window.history.replaceState(null, "", p); else onLeave(cw.location.href);
          onTitle(cw.document.title);
        } catch { /* frame navigated away mid-sync */ }
      };
      const { pushState, replaceState } = cw.history;
      cw.history.pushState = function (...a: Parameters<History["pushState"]>) { pushState.apply(this, a); sync(); };
      cw.history.replaceState = function (...a: Parameters<History["replaceState"]>) { replaceState.apply(this, a); sync(); };
      cw.addEventListener("popstate", sync);
      cw.addEventListener("hashchange", sync);
      detach = () => {
        try {
          cw.history.pushState = pushState; cw.history.replaceState = replaceState;
          cw.removeEventListener("popstate", sync); cw.removeEventListener("hashchange", sync);
        } catch { /* frame gone */ }
        detach = () => {};
      };
      sync();
    };
    frame.addEventListener("load", attach);
    return () => { frame.removeEventListener("load", attach); detach(); };
  }, [ref, tile, onLeave, onTitle]);
  return blocked;
}
