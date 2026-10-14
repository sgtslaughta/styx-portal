import { useEffect, useState } from "react";
import { Info, Plus, X } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { Badge } from "@/components/ui/badge";
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
  "flex min-w-0 flex-1 items-center gap-2.5 rounded-lg border border-border bg-card px-3 min-h-16 py-3 text-left text-sm " +
  "transition-colors hover:bg-accent outline-none focus-visible:ring-2 focus-visible:ring-ring";

function readDismissed(): boolean {
  try { return localStorage.getItem(TIP_KEY) === "1"; } catch { return false; }
}

function Tile({ s, focused, choose }: { s: ServiceTile; focused: boolean; choose: ReturnType<typeof useOpenChoice> }) {
  const h = HEALTH(s.up);
  const href = shellHref(s);
  // Unhealthy tiles stay clickable: health is advisory, the app may still work.
  return (
    <div className="flex w-full items-stretch gap-2">
      <a href={href} className={cn(tileCls, focused && "border-obol-foreground dark:border-obol")} aria-label={s.needs_setup ? `Set up ${s.name}` : `Open ${s.name}`} aria-current={focused ? "true" : undefined} title={href}
        onClick={(e) => {
          // Native new-tab gestures and the admin setup link keep plain link behaviour.
          if (s.needs_setup || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
          e.preventDefault();
          choose("apps", s.name, (mode) => openHref(mode, href));
        }}>
        <ServiceIcon s={s} />
        <span className="min-w-0 flex-1">
          <span className="block truncate font-medium">{s.name}</span>
          {s.mount_mode === "cookie-root" && <span className="block text-xs text-muted-foreground">Opens full screen</span>}
        </span>
        {s.needs_setup ? (
          <Badge variant="outline" className="border-destructive/40 text-destructive">Needs setup</Badge>
        ) : (
          <span className="flex items-center gap-1.5" title={h.label}>
            <span className={cn("size-2.5 shrink-0 rounded-full", h.dot)} aria-hidden />
            <span className="sr-only">{h.label}</span>
          </span>
        )}
      </a>
      {focused && (
        <Button asChild variant="outline" size="sm" className="h-auto self-stretch">
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
      <ul className="grid grid-cols-[repeat(auto-fill,minmax(15rem,1fr))] gap-3">
        {tiles.map((s) => <li key={s.id} className="flex"><Tile s={s} focused={!!focus?.slug && focus.slug === s.slug} choose={choose} /></li>)}
        {isAdmin && <li className="flex"><AddAppTile onClick={onOpenSettings} /></li>}
      </ul>
    </section>
  );
}
