import { useEffect, useState } from "react";
import { WaveTransition } from "@/components/effects/wave-transition";

/** Decode the {url,label} payload from the hash. Resolve the target against our
 *  own origin and accept ONLY same-origin destinations — session URLs are always
 *  portal-origin (instance "/i/…", workstation "https://DOMAIN/w/…"). This blocks
 *  open-redirect/phishing via a crafted "/connecting#…" link, and normalising to
 *  a relative path also defuses "javascript:"/"//host" payloads (their resolved
 *  origin never matches). */
function parseHash(): { url: string; label: string } | null {
  try {
    const raw = decodeURIComponent(window.location.hash.slice(1));
    if (!raw) return null;
    const data = JSON.parse(raw) as { url?: unknown; label?: unknown };
    if (typeof data.url !== "string") return null;
    const resolved = new URL(data.url, window.location.origin);
    if (resolved.origin !== window.location.origin) return null;
    return {
      url: resolved.pathname + resolved.search + resolved.hash,
      label: typeof data.label === "string" ? data.label : "",
    };
  } catch {
    return null;
  }
}

/**
 * New-tab interstitial: plays the wave wipe, then replaces itself with the
 * real session URL so the animation covers the connect/load instead of a
 * blank tab. Reached only via {@link openConnectWipe}.
 */
export function ConnectingPage() {
  const [target] = useState(parseHash);
  const [show] = useState(true);

  useEffect(() => {
    if (!target) return;
    // Hard fallback in case the animation's onDone never fires.
    const t = window.setTimeout(() => window.location.replace(target.url), 2000);
    return () => window.clearTimeout(t);
  }, [target]);

  function done() {
    if (target) window.location.replace(target.url);
  }

  return (
    <div className="fixed inset-0" style={{ background: "#0c1730" }}>
      <WaveTransition show={show} label={target?.label || "Connecting…"} onDone={done} />
      {!target && (
        <div className="flex h-full items-center justify-center text-sm text-white/70">
          Invalid connection link.
        </div>
      )}
    </div>
  );
}
