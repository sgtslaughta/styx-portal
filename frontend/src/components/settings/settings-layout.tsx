import { useMemo, useState } from "react";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { Button } from "@/components/ui/button";
import { SettingsNav } from "./settings-nav";
import { visibleCategories, type SettingsSection } from "./nav-config";
import { useAuth } from "@/hooks/use-auth";

export function SettingsLayout() {
  const { user, loading } = useAuth();
  const reduce = useReducedMotion();
  const cats = useMemo(() => visibleCategories(user?.role === "admin"), [user?.role]);
  const sections = useMemo(() => cats.flatMap((c) => c.sections), [cats]);
  const [activeId, setActiveId] = useState<string | undefined>(undefined);

  const active: SettingsSection | undefined =
    sections.find((s) => s.id === activeId) ?? sections[0];

  if (loading) {
    return <div className="mx-auto h-64 max-w-6xl animate-pulse rounded-lg bg-muted/30" />;
  }
  if (!active) return null;

  const Section = active.Component;
  return (
    <div className="mx-auto flex max-w-6xl flex-col md:flex-row md:gap-6">
      <SettingsNav categories={cats} activeId={active.id} onSelect={setActiveId} />
      <div className="min-w-0 flex-1 md:pl-0">
        {/* Mobile section selector (horizontal scrollable) */}
        <div className="mb-4 -mx-6 md:hidden">
          <div className="flex gap-2 overflow-x-auto px-6 pb-3 sm:overflow-x-visible">
            {sections.map((s) => {
              const Icon = s.icon;
              const isActive = s.id === activeId;
              return (
                <Button
                  key={s.id}
                  onClick={() => setActiveId(s.id)}
                  variant={isActive ? "default" : "outline"}
                  size="sm"
                  className="flex shrink-0 items-center gap-1.5 whitespace-nowrap"
                >
                  <Icon className="h-4 w-4" />
                  {s.label}
                </Button>
              );
            })}
          </div>
        </div>

        {/* Section header */}
        <div className="mb-6 space-y-1">
          <h2 className="text-2xl font-semibold tracking-tight">{active.label}</h2>
          <p className="text-sm text-muted-foreground">{active.description}</p>
        </div>

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
