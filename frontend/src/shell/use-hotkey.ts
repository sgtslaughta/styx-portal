import { useEffect, useRef } from "react";

const isHotkey = (e: KeyboardEvent) => e.altKey && e.shiftKey && !e.ctrlKey && !e.metaKey && e.code === "KeyS";

/** Alt+Shift+S (and Escape, via onEscape) on each target window. `frame` re-attaches on every load (the framed document is replaced). */
export function useHotkey(targets: () => (Window | null)[], onToggle: () => void, frame?: HTMLIFrameElement | null, onEscape?: () => void) {
  const latest = useRef({ targets, onToggle, onEscape });
  latest.current = { targets, onToggle, onEscape };
  useEffect(() => {
    let attached: Window[] = [];
    const handler = (e: KeyboardEvent) => {
      if (isHotkey(e)) { e.preventDefault(); latest.current.onToggle(); }
      else if (e.key === "Escape") latest.current.onEscape?.(); // an app's focus trap can keep keys inside the frame
    };
    const detach = () => {
      for (const w of attached) { try { w.removeEventListener("keydown", handler); } catch { /* gone */ } }
      attached = [];
    };
    const attach = () => {
      detach();
      let list: (Window | null)[] = [];
      try { list = latest.current.targets(); } catch { /* cross-origin */ }
      for (const w of list) {
        if (!w) continue;
        try { w.addEventListener("keydown", handler); attached.push(w); } catch { /* cross-origin navigation */ }
      }
    };
    attach();
    frame?.addEventListener("load", attach);
    return () => { frame?.removeEventListener("load", attach); detach(); };
  }, [frame]);
}
