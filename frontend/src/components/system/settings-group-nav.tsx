import { SlidersHorizontal } from "lucide-react";
import { cn } from "@/lib/utils";

type Item = { id: string; label: string; dirty: boolean };
type Props = { items: Item[]; activeId: string; onSelect: (id: string) => void };

export function SettingsGroupNav({ items, activeId, onSelect }: Props) {
  return (
    <nav
      aria-label="Setting groups"
      className="flex gap-1 overflow-x-auto pb-1 md:sticky md:top-4 md:w-48 md:shrink-0 md:flex-col md:self-start md:overflow-visible md:border-r md:border-border md:pb-0 md:pr-4"
    >
      {items.map((it) => {
        const active = it.id === activeId;
        return (
          <button
            key={it.id}
            type="button"
            onClick={() => onSelect(it.id)}
            aria-current={active ? "page" : undefined}
            className={cn(
              "relative flex shrink-0 items-center gap-2 rounded-md px-3 py-2 text-sm font-medium transition-colors",
              active
                ? "bg-primary/15 text-foreground"
                : "text-muted-foreground hover:bg-muted/40 hover:text-foreground",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            )}
          >
            <SlidersHorizontal className="h-4 w-4 shrink-0" />
            <span className="min-w-0 flex-1 truncate text-left">{it.label}</span>
            {it.dirty && (
              <span
                data-testid={`dirty-${it.id}`}
                title="Unsaved changes"
                className="h-2 w-2 shrink-0 rounded-full bg-primary"
              />
            )}
          </button>
        );
      })}
    </nav>
  );
}
