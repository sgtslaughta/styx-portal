import { useState } from "react";
import { cn } from "@/lib/utils";
import { MetricsOverview } from "./metrics-overview";
import { MetricsSessions } from "./metrics-sessions";
import { MetricsResources } from "./metrics-resources";
import { MetricsLogs } from "./metrics-logs";
import { ImageManager } from "./image-manager";
import { Activity, Terminal, Cpu, ScrollText, HardDrive } from "lucide-react";

const SUBTABS = [
  { id: "overview", label: "Overview", icon: Activity },
  { id: "sessions", label: "Sessions", icon: Terminal },
  { id: "resources", label: "Resources", icon: Cpu },
  { id: "logs", label: "Logs", icon: ScrollText },
  { id: "images", label: "Images", icon: HardDrive },
] as const;

type SubTab = (typeof SUBTABS)[number]["id"];

export function MetricsDashboard() {
  const [activeTab, setActiveTab] = useState<SubTab>("overview");

  return (
    <div className="space-y-4">
      {/* Sub-navigation */}
      <div className="flex items-center gap-1 rounded-lg bg-card border border-border p-1">
        {SUBTABS.map((tab) => {
          const Icon = tab.icon;
          return (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={cn(
                "flex items-center gap-2 rounded-md px-3 py-1.5 text-xs font-medium transition-all",
                activeTab === tab.id
                  ? "bg-secondary text-emerald-400 shadow-sm shadow-emerald-500/10"
                  : "text-muted-foreground hover:text-foreground/80 hover:bg-muted/40"
              )}
            >
              <Icon className="h-3.5 w-3.5" />
              {tab.label}
            </button>
          );
        })}
      </div>

      {/* Content */}
      <div className="min-h-[500px]">
        {activeTab === "overview" && <MetricsOverview />}
        {activeTab === "sessions" && <MetricsSessions />}
        {activeTab === "resources" && <MetricsResources />}
        {activeTab === "logs" && <MetricsLogs />}
        {activeTab === "images" && <ImageManager />}
      </div>
    </div>
  );
}
