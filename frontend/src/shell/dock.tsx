import { useEffect, useRef, useState, type RefObject } from "react";
import { AnimatePresence, m, type Variants } from "framer-motion";
import { ExternalLink, House, LogOut } from "lucide-react";
import { Dialog as DialogPrimitive } from "radix-ui";
import type { ServiceTile } from "@/api/client";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ServiceIcon } from "@/components/system/service-icon";
import { spring } from "@/lib/motion";
import { HEALTH, shellHref } from "@/lib/service-tiles";
import { DockWorkspaces } from "./dock-workspaces";
import { frameSrc } from "./url";

const K = 0.15; // px of curve per step² along the arc
const MAX_ARC = 4; // keep long lists inside the panel
const isPhone = () => window.matchMedia?.("(max-width: 639px)").matches ?? false;
const ACTION = "inline-flex min-h-11 items-center rounded-md px-3 text-sm font-semibold text-foreground hover:bg-foreground/10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring";

type Props = {
  open: boolean; onOpenChange: (open: boolean) => void; tiles: ServiceTile[];
  current: string; focusSlug: string | null; side: "left" | "right"; tabRef?: RefObject<HTMLElement | null>;
};

export function Dock({ open, onOpenChange, tiles, current, focusSlug, side, tabRef }: Props) {
  const contentRef = useRef<HTMLDivElement>(null);
  const wasOpen = useRef(false);
  const [view, setView] = useState("apps");
  // Radix autofocus skips forceMount+AnimatePresence; focus by hand so Esc works after an iframe hotkey
  useEffect(() => {
    if (open) {
      let id = 0;
      let tries = 0;
      const focusIn = () => {
        const el = contentRef.current; // the portal mounts a frame or two after `open` flips
        if (!el) { if (tries++ < 10) id = requestAnimationFrame(focusIn); return; }
        const ae = document.activeElement; // the dialog's focus trap may land on the first tabbable: the switch
        if (!el.contains(ae) || ae === el || ae?.getAttribute("role") === "tab")
          (el.querySelector<HTMLElement>('a[aria-current="page"]') ?? el.querySelector<HTMLElement>("a") ?? (ae?.getAttribute("role") === "tab" ? (ae as HTMLElement) : el)).focus();
      };
      id = requestAnimationFrame(focusIn);
      wasOpen.current = true;
      return () => cancelAnimationFrame(id);
    }
    if (wasOpen.current) tabRef?.current?.focus();
    wasOpen.current = false;
  }, [open, tabRef]);
  const phone = open && isPhone();
  const dir = side === "right" ? 1 : -1;
  const mid = (tiles.length - 1) / 2;
  const item: Variants = {
    hidden: { x: phone ? 0 : dir * 12, opacity: 0 },
    show: (i: number) => ({ x: phone ? 0 : dir * Math.min(K * (i - mid) ** 2, MAX_ARC), opacity: 1, transition: spring }),
  };
  const list: Variants = { hidden: {}, show: { transition: { staggerChildren: 0.025, delayChildren: 0.06 } } };
  const cur = tiles.find((t) => t.slug === current);
  return (
    <DialogPrimitive.Root open={open} onOpenChange={onOpenChange}>
      <AnimatePresence onExitComplete={() => setView("apps")}>
        {open && (
          <DialogPrimitive.Portal forceMount>
            <DialogPrimitive.Overlay forceMount asChild>
              <m.div className="fixed inset-0 z-50 bg-black/20" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} />
            </DialogPrimitive.Overlay>
            <DialogPrimitive.Content forceMount asChild>
              <m.div ref={contentRef} tabIndex={-1}
                initial={phone ? { y: 24, opacity: 0 } : { x: dir * 24, opacity: 0 }} animate={{ x: 0, y: 0, opacity: 1 }}
                exit={phone ? { y: 24, opacity: 0 } : { x: dir * 24, opacity: 0 }}
                transition={spring}
                className={`fixed z-50 outline-none flex flex-col gap-3 border border-border bg-background/80 p-4 text-foreground shadow-xl backdrop-blur-xl dark:bg-card/80
                  inset-x-0 bottom-0 max-h-[80dvh] pb-[max(1rem,env(safe-area-inset-bottom))] rounded-t-2xl
                  sm:inset-x-auto sm:inset-y-0 sm:max-h-none sm:w-[min(22rem,calc(100vw-32px))] sm:rounded-none ${side === "right" ? "sm:right-0" : "sm:left-0"}`}
              >
                <DialogPrimitive.Title className="sr-only">Styx</DialogPrimitive.Title>
                <DialogPrimitive.Description className="sr-only">Switch apps or workspaces, or go back to Styx</DialogPrimitive.Description>
                <Tabs value={view} onValueChange={setView} className="min-h-0 flex-1">
                  <TabsList aria-label="Switch list" className="w-full border border-border bg-foreground/10 group-data-[orientation=horizontal]/tabs:h-11 sm:group-data-[orientation=horizontal]/tabs:h-9">
                    <TabsTrigger value="apps" className="flex-1">Apps</TabsTrigger>
                    <TabsTrigger value="workspaces" className="flex-1">Workspaces</TabsTrigger>
                  </TabsList>
                  <TabsContent value="apps" className="flex min-h-0 flex-col">
                    {tiles.length === 0 ? <p className="py-6 text-foreground">No apps yet</p> : (
                      <m.ul variants={list} initial="hidden" animate="show" className="flex flex-1 flex-col gap-1 overflow-y-auto px-2 py-1">
                        {tiles.map((t, i) => {
                          const h = HEALTH(t.up);
                          const active = t.slug === current;
                          return (
                            <m.li key={t.id} custom={i} variants={item}>
                              <a href={shellHref(t)} target="_top" aria-current={active ? "page" : undefined}
                                className={`flex min-h-12 items-center gap-3 rounded-md border px-3 hover:bg-foreground/10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${active ? "border-obol-foreground dark:border-obol" : "border-transparent"}`}>
                                <ServiceIcon s={t} />
                                <span className="flex-1 truncate">{t.name}</span>
                                <span className={`size-2.5 rounded-full ${h.dot}`} aria-hidden />
                                <span className="sr-only">{h.label}</span>
                              </a>
                            </m.li>
                          );
                        })}
                      </m.ul>
                    )}
                  </TabsContent>
                  <TabsContent value="workspaces" className="flex min-h-0 flex-col">
                    <DockWorkspaces onPicked={() => onOpenChange(false)} />
                  </TabsContent>
                </Tabs>
                <div className="flex flex-wrap gap-1 border-t border-border px-2 pt-3">
                  <a href="/_styx/exit?next=/" target="_top" className={ACTION}><House className="mr-2 size-4" aria-hidden />Home</a>
                  {cur && <a href={frameSrc(cur.mount_mode, cur.slug, "/")} target="_blank" rel="noopener" className={ACTION}><ExternalLink className="mr-2 size-4" aria-hidden />Pop out</a>}
                  {focusSlug === current && <a href="/_styx/exit?next=/" target="_top" className={ACTION}><LogOut className="mr-2 size-4" aria-hidden />Exit focus</a>}
                </div>
              </m.div>
            </DialogPrimitive.Content>
          </DialogPrimitive.Portal>
        )}
      </AnimatePresence>
    </DialogPrimitive.Root>
  );
}
