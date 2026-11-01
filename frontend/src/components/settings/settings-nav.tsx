import { useMemo, useState } from "react";
import { Search } from "lucide-react";
import { cn } from "@/lib/utils";
import { filterCategories, type SettingsCategory } from "./nav-config";
import { useUnsaved } from "./unsaved-context";

type Props = {
  categories: SettingsCategory[];
  activeId: string;
  onSelect: (id: string) => void;
};

export function SettingsNav({ categories, activeId, onSelect }: Props) {
  const { confirmLeave } = useUnsaved();
  const [q, setQ] = useState("");
  const shown = useMemo(() => filterCategories(categories, q), [categories, q]);

  const go = (id: string) => {
    if (id !== activeId) confirmLeave(() => onSelect(id));
  };

  return (
    <nav
      aria-label="Admin sections"
      className="hidden md:sticky md:top-0 md:block md:max-h-[calc(100dvh-100px)] md:w-[210px] md:shrink-0 md:self-start md:overflow-y-auto"
    >
      <label className="mb-3.5 flex items-center gap-2 rounded-lg border border-border bg-card px-2.5 py-1.5 text-muted-foreground focus-within:ring-2 focus-within:ring-ring">
        <Search className="h-4 w-4 shrink-0" />
        <input
          type="search"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Find a setting"
          aria-label="Find a setting"
          className="w-full bg-transparent text-[13.5px] text-foreground outline-none placeholder:text-muted-foreground"
        />
      </label>
      {shown.length === 0 && <p className="px-2 text-sm text-muted-foreground">No matching settings.</p>}
      {shown.map((cat) => (
        <div key={cat.id} className="mb-4">
          <h4 className="mb-1 px-2 text-xs font-medium text-muted-foreground">{cat.label}</h4>
          <ul className="space-y-0.5">
            {cat.sections.map((s) => {
              const active = s.id === activeId;
              return (
                <li key={s.id}>
                  <button
                    onClick={() => go(s.id)}
                    aria-current={active ? "page" : undefined}
                    title={s.tooltip}
                    className={cn(
                      "flex w-full items-center rounded-md px-2 py-1.5 text-left text-sm transition-colors",
                      "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                      active
                        ? "gold-underline font-medium text-foreground"
                        : "text-muted-foreground hover:bg-muted/40 hover:text-foreground",
                    )}
                  >
                    {s.label}
                  </button>
                </li>
              );
            })}
          </ul>
        </div>
      ))}
    </nav>
  );
}
