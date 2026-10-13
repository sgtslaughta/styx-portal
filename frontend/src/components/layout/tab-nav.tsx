import { cn } from "@/lib/utils";

interface TabNavProps {
  activeTab: string;
  onTabChange: (tab: string) => void;
}

const TABS = [
  { id: "instances", label: "My instances" },
  { id: "templates", label: "Template gallery" },
  { id: "system", label: "Settings" },
];

export function TabNav({ activeTab, onTabChange }: TabNavProps) {
  return (
    <div className="flex gap-1 border-b border-border px-6 styx-header">
      {TABS.map((tab) => (
        <button
          key={tab.id}
          onClick={() => onTabChange(tab.id)}
          aria-current={activeTab === tab.id ? "page" : undefined}
          className={cn(
            "my-1.5 rounded-lg px-4 py-1.5 text-sm font-medium transition-colors outline-none focus-visible:ring-2 focus-visible:ring-ring max-sm:my-0 max-sm:min-h-11",
            "hover:text-foreground",
            activeTab === tab.id
              ? "bg-card text-foreground shadow-[inset_0_0_0_1px_var(--card-border-color)]"
              : "text-muted-foreground"
          )}
        >
          {tab.label}
        </button>
      ))}
    </div>
  );
}
