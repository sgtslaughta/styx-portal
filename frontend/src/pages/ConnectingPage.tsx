import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { WaveTransition } from "@/components/effects/wave-transition";

/** Decode the {url,label} payload from the hash. Resolve the target against our
 *  own origin and accept ONLY same-origin destinations — session URLs are always
 *  portal-origin (instance "/i/…", workstation "https://DOMAIN/w/…"). This blocks
 *  open-redirect/phishing via a crafted "/connecting#…" link, and normalising to
 *  a relative path also defuses "javascript:"/"//host" payloads (their resolved
 *  origin never matches). */
function parseHash(): { url: string | null; label: string } | null {
  try {
    const raw = decodeURIComponent(window.location.hash.slice(1));
    if (!raw) return null;
    const data = JSON.parse(raw) as { url?: unknown; label?: unknown };
    const label = typeof data.label === "string" ? data.label : "";
    if (data.url === undefined) return { url: null, label }; // pending: the opener sends the url later
    if (typeof data.url !== "string") return null;
    const resolved = new URL(data.url, window.location.origin);
    if (resolved.origin !== window.location.origin) return null;
    return { url: resolved.pathname + resolved.search + resolved.hash, label };
  } catch {
    return null;
  }
}

const PENDING_MS = 30_000;

/**
 * New-tab interstitial: plays the wave wipe, then replaces itself with the
 * real session URL so the animation covers the connect/load instead of a
 * blank tab. Reached via {@link openPending}.
 */
export function ConnectingPage() {
  const [target, setTarget] = useState(parseHash);
  const waveDone = useRef(false);
  const url = useRef<string | null>(null);
  url.current = target?.url ?? null;

  // A pending tab (opened before the connect call returned) gets its url via a hash change.
  useEffect(() => {
    const on = () => setTarget(parseHash());
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);

  // A pending tab whose opener never delivers a url would wave forever.
  const [stale, setStale] = useState(false);
  const pending = !!target && !target.url;
  useEffect(() => {
    if (!pending) { setStale(false); return; }
    const t = window.setTimeout(() => setStale(true), PENDING_MS);
    return () => window.clearTimeout(t);
  }, [pending]);

  useEffect(() => {
    const u = target?.url;
    if (!u) return;
    if (waveDone.current) { window.location.replace(u); return; }
    // Hard fallback in case the animation's onDone never fires.
    const t = window.setTimeout(() => window.location.replace(u), 2000);
    return () => window.clearTimeout(t);
  }, [target]);

  function done() {
    waveDone.current = true;
    if (url.current) window.location.replace(url.current);
  }

  return (
    <div className="fixed inset-0" style={{ background: "#0c1730" }}>
      <WaveTransition show label={target?.label || "Connecting…"} onDone={done} />
      {!target && (
        <div className="flex h-full items-center justify-center text-sm text-white/70">
          Invalid connection link.
        </div>
      )}
      {stale && pending && (
        <div className="absolute inset-0 z-10 flex flex-col items-center justify-center gap-3 bg-[#0c1730] text-sm text-white/80">
          <p>This connection didn&apos;t start.</p>
          <Button variant="outline" onClick={() => window.close()}>Close</Button>
        </div>
      )}
    </div>
  );
}
