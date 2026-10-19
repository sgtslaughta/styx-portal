import { cn } from "@/lib/utils";
import { readLocal, writeLocal } from "@/lib/local";

export type MainTab = "workspaces" | "apps" | "templates" | "system";

const HOME_KEY = "styx.home.tab"; // kept from the old Workspaces | Apps sub-tabs
const TABS: { id: MainTab; label: string }[] = [
  { id: "workspaces", label: "Workspaces" },
  { id: "apps", label: "Apps" },
  { id: "templates", label: "Templates" },
  { id: "system", label: "Settings" },
];

/** Landing tab: the last of Workspaces/Apps used in this browser. */
export function readHomeTab(): MainTab {
  return readLocal(HOME_KEY) === "apps" ? "apps" : "workspaces";
}

export function rememberHomeTab(tab: MainTab): void {
  if (tab === "workspaces" || tab === "apps") writeLocal(HOME_KEY, tab);
}

export function TabNav({ activeTab, onTabChange }: { activeTab: MainTab; onTabChange: (tab: MainTab) => void }) {
  return (
    <nav aria-label="Main" className="styx-header flex gap-1 overflow-x-auto border-b border-border px-6 [scrollbar-width:none] max-sm:px-4">
      {TABS.map((tab) => (
        <button
          key={tab.id}
          type="button"
          onClick={() => { rememberHomeTab(tab.id); onTabChange(tab.id); }}
          aria-current={activeTab === tab.id ? "page" : undefined}
          className={cn(
            "my-1.5 shrink-0 whitespace-nowrap rounded-lg px-4 py-1.5 text-sm font-medium transition-colors outline-none hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring max-sm:my-1 max-sm:min-h-11",
            activeTab === tab.id
              ? "bg-card text-foreground shadow-[inset_0_0_0_1px_var(--card-border-color)]"
              : "text-muted-foreground",
          )}
        >
          {tab.label}
        </button>
      ))}
    </nav>
  );
}
