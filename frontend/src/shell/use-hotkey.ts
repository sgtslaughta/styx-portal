import { useEffect, useRef } from "react";

const isHotkey = (e: KeyboardEvent) => e.altKey && e.shiftKey && !e.ctrlKey && !e.metaKey && e.code === "KeyS";

/** Alt+Shift+S on each target window. `frame` re-attaches on every load (the framed document is replaced). */
export function useHotkey(targets: () => (Window | null)[], onToggle: () => void, frame?: HTMLIFrameElement | null) {
  const latest = useRef({ targets, onToggle });
  latest.current = { targets, onToggle };
  useEffect(() => {
    let attached: Window[] = [];
    const handler = (e: KeyboardEvent) => { if (isHotkey(e)) { e.preventDefault(); latest.current.onToggle(); } };
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
