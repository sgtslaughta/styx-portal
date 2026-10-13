import { useEffect, useState } from "react";
import { Info, Link2, X } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { api, type ServiceTile } from "@/api/client";
import { useAuth } from "@/hooks/use-auth";
import { HEALTH, shellHref, toTile } from "@/lib/service-tiles";
import { cn } from "@/lib/utils";

const TIP_KEY = "styx.serviceTipDismissed";
const TIP = "Open apps with a non-admin account: proxied apps run with your Styx rights.";
const tileCls =
  "flex min-w-0 flex-1 items-center gap-2.5 rounded-lg border border-border bg-card px-3 py-2 text-left text-sm " +
  "transition-colors hover:bg-accent focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring";

function readDismissed(): boolean {
  try { return localStorage.getItem(TIP_KEY) === "1"; } catch { return false; }
}

function Tile({ s, focused }: { s: ServiceTile; focused: boolean }) {
  const h = HEALTH(s.up);
  const href = shellHref(s);
  // Unhealthy tiles stay clickable: health is advisory, the app may still work.
  return (
    <div className={cn("flex items-center gap-2 rounded-lg", focused && "ring-2 ring-obol")}>
      <a href={href} className={tileCls} aria-label={`Open ${s.name}`} aria-current={focused ? "true" : undefined} title={href}>
        <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-md bg-primary/10 text-base leading-none text-primary" aria-hidden>
          {s.icon ?? <Link2 className="h-3.5 w-3.5" />}
        </span>
        <span className="min-w-0 flex-1">
          <span className="block truncate font-medium">{s.name}</span>
          {s.mount_mode === "cookie-root" && <span className="block text-xs text-muted-foreground">Opens on its own</span>}
        </span>
        <span className="flex items-center gap-1.5">
          <span className={cn("h-2 w-2 shrink-0 rounded-full", h.dot)} aria-hidden />
          <span className="sr-only">{h.label}</span>
        </span>
      </a>
      {focused && (
        <a href="/_styx/exit?next=/" aria-label={`Exit ${s.name}`}
          className="mr-2 inline-flex min-h-11 shrink-0 items-center rounded px-3 py-1 text-xs sm:min-h-0 sm:px-2 font-medium text-obol-foreground underline underline-offset-2 focus-visible:outline-2 focus-visible:outline-ring">
          Exit
        </a>
      )}
    </div>
  );
}

export function ServiceList({ onOpenSettings }: { onOpenSettings?: () => void }) {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";
  const [tiles, setTiles] = useState<ServiceTile[] | null>(null);
  const { data: focus } = useQuery({ queryKey: ["service-focus"], queryFn: api.serviceFocus, refetchOnWindowFocus: true });
  const [tipHidden, setTipHidden] = useState(readDismissed);

  useEffect(() => {
    let live = true;
    const load = () => api.listServiceTiles()
      .then((r) => { if (live) setTiles(r.map(toTile).filter((x) => x.enabled)); })
      .catch(() => { if (live) setTiles((t) => t ?? []); });
    void load();
    const t = setInterval(load, 30_000);
    return () => { live = false; clearInterval(t); };
  }, []);

  if (tiles === null) return null;
  if (tiles.length === 0) {
    if (!isAdmin) return null;
    return (
      <p className="mb-4 rounded-lg border border-dashed border-border px-3 py-2 text-xs text-muted-foreground">
        No services yet. Add one in <button type="button" onClick={onOpenSettings}
          className="underline underline-offset-2 hover:text-foreground focus-visible:outline-2 focus-visible:outline-ring">Services in Settings</button>.
      </p>
    );
  }

  const dismiss = () => {
    setTipHidden(true);
    try { localStorage.setItem(TIP_KEY, "1"); } catch { /* ignore */ }
  };

  return (
    <section className="mb-4 space-y-2" aria-label="Services">
      <h3 className="text-sm font-medium text-muted-foreground">Services</h3>
      {isAdmin && !tipHidden && (
        <div className="flex items-start gap-2 rounded-md border border-border bg-muted/40 px-2.5 py-2 text-xs text-muted-foreground">
          <Info className="mt-px h-3.5 w-3.5 shrink-0 text-primary" aria-hidden />
          <p className="min-w-0 flex-1">{TIP}</p>
          <button type="button" aria-label="Dismiss tip" onClick={dismiss}
            className="-m-0.5 rounded p-0.5 hover:text-foreground focus-visible:outline-2 focus-visible:outline-ring">
            <X className="h-3.5 w-3.5" />
          </button>
        </div>
      )}
      <ul className="grid grid-cols-1 gap-2 sm:grid-cols-2">
        {tiles.map((s) => <li key={s.id}><Tile s={s} focused={!!focus?.slug && focus.slug === s.slug} /></li>)}
      </ul>
    </section>
  );
}
