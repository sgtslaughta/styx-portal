import { SectionHead } from "@/components/common/section-head";
import { useEffect, useMemo, useState } from "react";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { Button } from "@/components/ui/button";
import { SettingsNav } from "./settings-nav";
import { visibleCategories, type SettingsSection } from "./nav-config";
import { cn } from "@/lib/utils";
import { useAuth } from "@/hooks/use-auth";
import { useCfAnalytics } from "@/hooks/use-admin-stats";
import { UnsavedProvider, useUnsaved } from "./unsaved-context";

const ALIASES: Record<string, string> = { resources: "overview", groups: "users", settings: "security" };

export function SettingsLayout() {
  return <UnsavedProvider><SettingsLayoutInner /></UnsavedProvider>;
}

function SettingsLayoutInner() {
  const { confirmLeave } = useUnsaved();
  const { user, loading } = useAuth();
  const reduce = useReducedMotion();
  const isAdmin = user?.role === "admin";
  const cfAnalytics = useCfAnalytics(isAdmin);
  const cats = useMemo(() => visibleCategories(isAdmin, { cfAnalytics }), [isAdmin, cfAnalytics]);
  const sections = useMemo(() => cats.flatMap((c) => c.sections), [cats]);
  const [activeId, setActiveId] = useState<string | undefined>(
    () => (new URLSearchParams(window.location.search).has("setup") ? "services" : undefined));
  useEffect(() => {
    const go = (e: Event) => { const id = (e as CustomEvent<string>).detail; confirmLeave(() => setActiveId(ALIASES[id] ?? id)); };
    window.addEventListener("styx:settings-section", go);
    return () => window.removeEventListener("styx:settings-section", go);
  }, [confirmLeave]);

  const active: SettingsSection | undefined =
    sections.find((s) => s.id === activeId) ?? sections[0];

  if (loading) {
    return <div className="mx-auto h-64 max-w-screen-2xl animate-pulse rounded-lg bg-muted/30" />;
  }
  if (!active) return null;

  const Section = active.Component;
  return (
    <div className="mx-auto flex w-full max-w-[1640px] flex-col px-0 md:flex-row md:gap-6 2xl:gap-8">
      <SettingsNav categories={cats} activeId={active.id} onSelect={setActiveId} />
      <div className="min-w-0 flex-1 md:pl-0">
        {/* Mobile section selector (horizontal scrollable) */}
        <div className="mb-4 -mx-6 md:hidden">
          <div className="flex snap-x gap-2 overflow-x-auto scroll-px-6 px-6 pb-3 [scrollbar-width:none] [mask-image:linear-gradient(to_right,transparent,#000_24px,#000_calc(100%-24px),transparent)]">
            {sections.map((s) => {
              const Icon = s.icon;
              const isActive = s.id === active.id;
              return (
                <Button
                  key={s.id}
                  onClick={() => { if (!isActive) confirmLeave(() => setActiveId(s.id)); }}
                  variant="outline"
                  size="sm"
                  aria-current={isActive ? "page" : undefined}
                  ref={(el) => { if (isActive) el?.scrollIntoView?.({ inline: "nearest", block: "nearest" }); }}
                  className={cn("flex shrink-0 snap-start items-center gap-1.5 whitespace-nowrap", isActive && "border-primary/40 bg-primary/15 text-foreground dark:border-primary/40 dark:bg-primary/15")}
                >
                  <Icon className="h-4 w-4" />
                  {s.label}
                </Button>
              );
            })}
          </div>
        </div>

        {/* Section header */}
        <SectionHead size="page" title={active.label} note={active.description} />

        {/* Content pane */}
        <AnimatePresence mode="wait">
          <motion.div
            key={active.id}
            initial={reduce ? false : { opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={reduce ? undefined : { opacity: 0, y: -8 }}
            transition={{ duration: 0.18, ease: "easeOut" }}
          >
            <Section />
          </motion.div>
        </AnimatePresence>
      </div>
    </div>
  );
}
