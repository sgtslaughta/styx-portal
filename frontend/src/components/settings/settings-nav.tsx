import { useState } from "react";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { ChevronDown } from "lucide-react";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Tooltip, TooltipTrigger, TooltipContent } from "@/components/ui/tooltip";
import type { SettingsCategory } from "./nav-config";

type Props = {
  categories: SettingsCategory[];
  activeId: string;
  onSelect: (id: string) => void;
};

export function SettingsNav({ categories, activeId, onSelect }: Props) {
  const reduce = useReducedMotion();
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({});

  return (
    <nav className="hidden md:block md:w-56 md:shrink-0 md:space-y-5 md:border-r md:border-border md:pr-6">
      {categories.map((cat) => {
        const CatIcon = cat.icon;
        const isCollapsed = collapsed[cat.id];
        return (
          <div key={cat.id}>
            <button
              onClick={() => setCollapsed((c) => ({ ...c, [cat.id]: !c[cat.id] }))}
              className={cn(
                "flex w-full items-center gap-2 rounded-md px-3 py-2 text-xs font-semibold uppercase tracking-wide transition-colors",
                "text-muted-foreground hover:bg-muted/50 hover:text-foreground",
                "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              )}
            >
              <CatIcon className="h-4 w-4" />
              <span className="flex-1 text-left">{cat.label}</span>
              {cat.adminOnly && (
                <Badge variant="outline" className="px-1.5 py-0 text-[10px]">Admin</Badge>
              )}
              <ChevronDown className={cn("h-3.5 w-3.5 transition-transform duration-200", isCollapsed && "-rotate-90")} />
            </button>
            <AnimatePresence initial={false}>
              {!isCollapsed && (
                <motion.ul
                  initial={reduce ? false : { height: 0, opacity: 0 }}
                  animate={{ height: "auto", opacity: 1 }}
                  exit={reduce ? undefined : { height: 0, opacity: 0 }}
                  transition={{ duration: 0.18, ease: "easeOut" }}
                  className="mt-1 space-y-1 overflow-hidden"
                >
                  {cat.sections.map((s) => {
                    const Icon = s.icon;
                    const active = s.id === activeId;
                    return (
                      <li key={s.id}>
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <button
                              onClick={() => onSelect(s.id)}
                              className={cn(
                                "relative flex w-full items-center gap-2 rounded-md px-3 py-2 text-sm transition-colors",
                                active
                                  ? "text-foreground"
                                  : "text-muted-foreground hover:bg-muted/40 hover:text-foreground",
                                "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                              )}
                            >
                              {active && (
                                <motion.span
                                  layoutId="settings-active"
                                  className="absolute inset-0 rounded-md bg-primary/15"
                                  transition={reduce ? { duration: 0 } : { type: "spring", stiffness: 500, damping: 40 }}
                                />
                              )}
                              <Icon className="relative z-10 h-4 w-4" />
                              <span className="relative z-10 font-medium">{s.label}</span>
                            </button>
                          </TooltipTrigger>
                          <TooltipContent side="right">{s.tooltip}</TooltipContent>
                        </Tooltip>
                      </li>
                    );
                  })}
                </motion.ul>
              )}
            </AnimatePresence>
          </div>
        );
      })}
    </nav>
  );
}
