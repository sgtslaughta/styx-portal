import { cn } from "@/lib/utils";

interface TabNavProps {
  activeTab: string;
  onTabChange: (tab: string) => void;
}

const TABS = [
  { id: "instances", label: "My Instances" },
  { id: "templates", label: "Template Gallery" },
  { id: "system", label: "Settings" },
];

export function TabNav({ activeTab, onTabChange }: TabNavProps) {
  return (
    <div className="flex gap-1 border-b border-border px-6 styx-header">
      {TABS.map((tab) => (
        <button
          key={tab.id}
          onClick={() => onTabChange(tab.id)}
          className={cn(
            "my-1.5 rounded-lg px-4 py-1.5 text-sm font-medium transition-colors",
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
