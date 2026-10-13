import { useCallback, useEffect, useState } from "react";
import type { ServiceTile } from "@/api/client";
import { useFrameSync } from "./use-frame-sync";
import { frameSrc } from "./url";

const ALLOW = "fullscreen; clipboard-read; clipboard-write; autoplay; picture-in-picture; encrypted-media; camera; microphone; geolocation";

/** A previous focus app may have left a root-scoped service worker that would hijack Styx. */
async function clearRootWorkers() {
  try {
    const regs = (await navigator.serviceWorker?.getRegistrations()) ?? [];
    await Promise.all(regs.filter((r) => r.scope === `${location.origin}/`).map((r) => r.unregister()));
  } catch { /* best effort */ }
}

const BTN = "mt-4 inline-flex min-h-11 items-center rounded-md bg-primary px-4 font-semibold text-primary-foreground";

export function Card({ title, text, href, action, onAction }:
  { title: string; text: string; action: string; href?: string; onAction?: () => void }) {
  return (
    <main className="flex h-dvh w-screen items-center justify-center bg-background p-4">
      <div className="max-w-md rounded-lg border border-border bg-card p-6 text-card-foreground">
        <h1 className="text-xl font-semibold">{title}</h1>
        <p className="mt-2 text-muted-foreground">{text}</p>
        {onAction
          ? <button type="button" onClick={onAction} className={BTN}>{action}</button>
          : <a href={href} target="_top" className={BTN}>{action}</a>}
      </div>
    </main>
  );
}

type FrameProps = { tile: ServiceTile; inner: string; onTitle: (t: string) => void; onFrame?: (el: HTMLIFrameElement | null) => void };

export function Frame({ tile, inner, onTitle, onFrame }: FrameProps) {
  const [el, setEl] = useState<HTMLIFrameElement | null>(null);
  const setRef = useCallback((n: HTMLIFrameElement | null) => { setEl(n); onFrame?.(n); }, [onFrame]);
  const [ready, setReady] = useState(tile.mount_mode !== "cookie-root");
  useEffect(() => {
    if (tile.mount_mode === "cookie-root") void clearRootWorkers().then(() => setReady(true));
  }, [tile.mount_mode]);
  const onLeave = useCallback((href: string) => {
    try { if (new URL(href, location.href).origin === location.origin) window.location.assign(href); }
    catch { /* ignore malformed */ }
  }, []);
  const blocked = useFrameSync(el, tile, onLeave, onTitle);
  const src = frameSrc(tile.mount_mode, tile.slug, inner);
  if (blocked) {
    return <Card title={`${tile.name} can't run inside Styx`}
      text="This app blocks being shown inside another page." href={src} action={`Open ${tile.name} on its own`} />;
  }
  if (!ready) return null;
  return <iframe ref={setRef} title={tile.name} src={src} className="h-full w-full border-0" allow={ALLOW} />;
}
