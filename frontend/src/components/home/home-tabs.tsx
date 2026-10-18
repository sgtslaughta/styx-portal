import { useState, type ReactNode } from "react";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

const KEY = "styx.home.tab";
type Tab = "workspaces" | "apps";

function readTab(): Tab {
  try { return localStorage.getItem(KEY) === "apps" ? "apps" : "workspaces"; } catch { return "workspaces"; }
}

/** Workspaces | Apps switch at the top of home; the last tab is remembered per browser. */
export function HomeTabs({ workspaces, apps }: { workspaces: ReactNode; apps: ReactNode }) {
  const [tab, setTab] = useState(readTab);
  function change(v: string) {
    const t: Tab = v === "apps" ? "apps" : "workspaces";
    setTab(t);
    try { localStorage.setItem(KEY, t); } catch { /* storage blocked: session-only */ }
  }
  return (
    <Tabs value={tab} onValueChange={change} className="h-full min-h-0">
      <TabsList aria-label="Home" className="max-sm:group-data-[orientation=horizontal]/tabs:h-11">
        <TabsTrigger value="workspaces" className="px-4">Workspaces</TabsTrigger>
        <TabsTrigger value="apps" className="px-4">Apps</TabsTrigger>
      </TabsList>
      <TabsContent value="workspaces" forceMount className="min-h-0 flex-1 data-[state=inactive]:hidden">{workspaces}</TabsContent>
      <TabsContent value="apps" forceMount className="relative min-h-0 flex-1 overflow-y-auto data-[state=inactive]:hidden">{apps}</TabsContent>
    </Tabs>
  );
}
