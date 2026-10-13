import type { RefObject } from "react";
import { AnimatePresence, m, type Variants } from "framer-motion";
import { Dialog as DialogPrimitive } from "radix-ui";
import type { ServiceTile } from "@/api/client";
import { spring } from "@/lib/motion";
import { HEALTH, shellHref } from "@/lib/service-tiles";
import { frameSrc } from "./url";

const K = 0.6; // px of curve per step² along the arc
const MAX_ARC = 12; // keep long lists inside the panel
const isPhone = () => window.matchMedia?.("(max-width: 639px)").matches ?? false;
const ACTION = "inline-flex min-h-11 items-center rounded-md px-3 text-sm font-semibold text-foreground hover:bg-foreground/10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring";

type Props = {
  open: boolean; onOpenChange: (open: boolean) => void; tiles: ServiceTile[];
  current: string; focusSlug: string | null; side: "left" | "right"; tabRef?: RefObject<HTMLElement | null>;
};

export function Dock({ open, onOpenChange, tiles, current, focusSlug, side, tabRef }: Props) {
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
      <AnimatePresence>
        {open && (
          <DialogPrimitive.Portal forceMount>
            <DialogPrimitive.Overlay forceMount asChild>
              <m.div className="fixed inset-0 z-50 bg-black/20" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} />
            </DialogPrimitive.Overlay>
            <DialogPrimitive.Content forceMount asChild
              onCloseAutoFocus={(e) => { e.preventDefault(); tabRef?.current?.focus(); }}>
              <m.div
                initial={phone ? { y: 24, opacity: 0 } : { x: dir * 24, opacity: 0 }} animate={{ x: 0, y: 0, opacity: 1 }}
                exit={phone ? { y: 24, opacity: 0 } : { x: dir * 24, opacity: 0 }}
                transition={spring}
                className={`fixed z-50 flex flex-col gap-3 border border-foreground/12 bg-background/80 p-4 text-foreground shadow-xl backdrop-blur-xl dark:border-white/10 dark:bg-background/72
                  inset-x-0 bottom-0 max-h-[80dvh] pb-[max(1rem,env(safe-area-inset-bottom))] rounded-t-2xl
                  sm:inset-x-auto sm:inset-y-0 sm:max-h-none sm:w-[min(22rem,calc(100vw-32px))] sm:rounded-none ${side === "right" ? "sm:right-0" : "sm:left-0"}`}
              >
                <DialogPrimitive.Title className="sr-only">Styx</DialogPrimitive.Title>
                <DialogPrimitive.Description className="sr-only">Switch apps or go back to Styx</DialogPrimitive.Description>
                {tiles.length === 0 ? <p className="py-6 text-foreground">No apps yet</p> : (
                  <m.ul variants={list} initial="hidden" animate="show" className="flex flex-1 flex-col gap-1 overflow-y-auto p-1">
                    {tiles.map((t, i) => {
                      const h = HEALTH(t.up);
                      const active = t.slug === current;
                      return (
                        <m.li key={t.id} custom={i} variants={item}>
                          <a href={shellHref(t)} target="_top" aria-current={active ? "page" : undefined}
                            className={`flex min-h-12 items-center gap-3 rounded-md px-3 hover:bg-foreground/10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${active ? "ring-2 ring-obol" : ""}`}>
                            {t.icon ? <img src={t.icon} alt="" className="size-7 rounded" /> : <span aria-hidden className="size-7 rounded bg-primary/20" />}
                            <span className="flex-1 truncate">{t.name}</span>
                            <span className={`size-2.5 rounded-full ${h.dot}`} aria-hidden />
                            <span className="sr-only">{h.label}</span>
                          </a>
                        </m.li>
                      );
                    })}
                  </m.ul>
                )}
                <div className="flex flex-wrap gap-1 border-t border-foreground/12 pt-3">
                  <a href="/_styx/exit?next=/" target="_top" className={ACTION}>Home</a>
                  {cur && <a href={frameSrc(cur.mount_mode, cur.slug, "/")} target="_blank" rel="noopener" className={ACTION}>Pop out</a>}
                  {focusSlug === current && <a href="/_styx/exit?next=/" target="_top" className={ACTION}>Exit focus</a>}
                </div>
              </m.div>
            </DialogPrimitive.Content>
          </DialogPrimitive.Portal>
        )}
      </AnimatePresence>
    </DialogPrimitive.Root>
  );
}
