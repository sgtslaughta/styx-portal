import { useEffect, useRef, useState } from "react";
import { Info, Plus, X } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { api, type ServiceTile } from "@/api/client";
import { useOpenChoice } from "@/components/open-prompt";
import { ServiceIcon } from "@/components/system/service-icon";
import { useAuth } from "@/hooks/use-auth";
import { openHref } from "@/lib/connect-wipe";
import { HEALTH, shellHref, toTile } from "@/lib/service-tiles";
import { cn } from "@/lib/utils";

const TIP_KEY = "styx.serviceTipDismissed";
const TIP = "Open apps with a non-admin account: proxied apps run with your Styx rights.";
const tileCls =
  "flex min-h-12 min-w-0 flex-1 items-center justify-center gap-2.5 rounded-lg border border-border bg-card px-3 py-3 text-sm " +
  "transition-colors hover:bg-accent outline-none focus-visible:ring-2 focus-visible:ring-ring";
const dockCls =
  "relative grid w-20 justify-items-center max-sm:w-full gap-2 rounded-xl border border-transparent p-1 text-center text-[13px] text-muted-foreground " +
  "transition-colors hover:text-foreground outline-none focus-visible:ring-2 focus-visible:ring-ring";

function readDismissed(): boolean {
  try { return localStorage.getItem(TIP_KEY) === "1"; } catch { return false; }
}

function Tile({ s, focused, choose, isAdmin }: { s: ServiceTile; focused: boolean; choose: ReturnType<typeof useOpenChoice>; isAdmin: boolean }) {
  const h = HEALTH(s.up);
  const href = shellHref(s);
  // Unhealthy apps stay clickable: health is advisory, the app may still work.
  return (
    <div className="flex flex-col items-center gap-1">
      <a href={href} className={cn(dockCls, focused && "border-obol-foreground dark:border-obol")} aria-label={s.needs_setup ? `Set up ${s.name}` : `Open ${s.name}`} aria-current={focused ? "true" : undefined} title={href}
        onClick={(e) => {
          // Native new-tab gestures and the admin setup link keep plain link behaviour.
          if (s.needs_setup || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
          e.preventDefault();
          choose("apps", s.name, (mode) => openHref(mode, href));
        }}>
        <span className="relative">
          <ServiceIcon s={s} className="size-[52px] rounded-[14px] shadow-md" />
          {s.needs_setup && isAdmin && (
            <span className="absolute -right-[3px] -top-[3px] size-3 rounded-full border-2 border-background bg-destructive" aria-hidden />
          )}
          {!s.needs_setup && (
            <span className={cn("absolute -bottom-0.5 -right-0.5 size-2.5 rounded-full", h.dot)} aria-hidden />
          )}
        </span>
        <span className="block w-full truncate">{s.name}</span>
        {s.needs_setup && isAdmin && <span className="sr-only">Needs setup</span>}
        {!s.needs_setup && <span className="sr-only">{h.label}</span>}
        {s.mount_mode === "cookie-root" && <span className="sr-only">Opens full screen</span>}
      </a>
      {focused && (
        <Button asChild variant="outline" size="sm" className="h-auto">
          <a href="/_styx/exit?next=/" aria-label={`Exit ${s.name}`}>Exit</a>
        </Button>
      )}
    </div>
  );
}

function AddAppTile({ onClick }: { onClick?: () => void }) {
  return (
    <button type="button" onClick={onClick}
      className={cn(tileCls, "justify-center border-dashed text-muted-foreground hover:text-foreground")}>
      <Plus className="size-4" aria-hidden />Add app
    </button>
  );
}

export function AppsGrid({ onOpenSettings }: { onOpenSettings?: () => void }) {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";
  const choose = useOpenChoice();
  const [tiles, setTiles] = useState<ServiceTile[] | null>(null);
  const { data: focus } = useQuery({ queryKey: ["service-focus"], queryFn: api.serviceFocus, refetchOnWindowFocus: true });
  const reload = useRef<() => void>(() => {});
  const [failed, setFailed] = useState(false);
  const [tipHidden, setTipHidden] = useState(readDismissed);

  useEffect(() => {
    let live = true;
    const load = () => api.listServiceTiles()
      .then((r) => { if (live) { setTiles(r.map(toTile).filter((x) => x.enabled)); setFailed(false); } })
      .catch(() => { if (live) { setFailed(true); setTiles((t) => t ?? []); } });
    reload.current = () => void load();
    void load();
    const t = setInterval(load, 30_000);
    return () => { live = false; clearInterval(t); };
  }, []);

  if (tiles === null) return null;
  if (failed && tiles.length === 0) {
    return (
      <section aria-label="Apps" className="space-y-3">
        <p className="text-sm text-muted-foreground">Couldn&apos;t load apps.</p>
        <Button variant="outline" size="sm" onClick={() => reload.current()}>Try again</Button>
      </section>
    );
  }
  if (tiles.length === 0) {
    return (
      <section aria-label="Apps" className="space-y-3">
        <p className="text-sm text-muted-foreground">
          {isAdmin ? "No apps yet. Add your first app." : "No apps shared with you yet."}
        </p>
        {isAdmin && <div className="flex max-w-xs"><AddAppTile onClick={onOpenSettings} /></div>}
      </section>
    );
  }

  const dismiss = () => {
    setTipHidden(true);
    try { localStorage.setItem(TIP_KEY, "1"); } catch { /* ignore */ }
  };

  return (
    <section className="space-y-3" aria-label="Apps">
      {isAdmin && !tipHidden && (
        <div className="flex items-start gap-2 rounded-md border border-border bg-muted/40 px-2.5 py-2 text-xs text-muted-foreground">
          <Info className="mt-px h-3.5 w-3.5 shrink-0 text-primary" aria-hidden />
          <p className="min-w-0 flex-1">{TIP}</p>
          <button type="button" aria-label="Dismiss tip" onClick={dismiss}
            className="-m-2 inline-flex size-11 shrink-0 items-center justify-center rounded hover:text-foreground focus-visible:outline-2 focus-visible:outline-ring">
            <X className="h-3.5 w-3.5" />
          </button>
        </div>
      )}
      <ul className="grid grid-cols-4 gap-x-2 gap-y-3 sm:flex sm:flex-wrap sm:gap-[18px]">
        {tiles.map((s) => <li key={s.id}><Tile s={s} focused={!!focus?.slug && focus.slug === s.slug} choose={choose} isAdmin={isAdmin} /></li>)}
        {isAdmin && <li className="col-span-4 flex sm:col-span-1"><AddAppTile onClick={onOpenSettings} /></li>}
      </ul>
    </section>
  );
}
