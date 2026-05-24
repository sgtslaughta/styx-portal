import { useState } from "react";
import { Header } from "@/components/layout/header";
import { TabNav } from "@/components/layout/tab-nav";
import { InstanceGrid } from "@/components/instances/instance-grid";
import type { Instance } from "@/lib/types";

export default function App() {
  const [activeTab, setActiveTab] = useState("instances");
  const [_selectedInstance, setSelectedInstance] = useState<Instance | null>(null);

  return (
    <div className="flex min-h-screen flex-col bg-background">
      <Header />
      <TabNav activeTab={activeTab} onTabChange={setActiveTab} />
      <main className="flex-1 p-6">
        {activeTab === "instances" && (
          <InstanceGrid onSelect={setSelectedInstance} onLaunch={() => setActiveTab("templates")} />
        )}
        {activeTab === "templates" && (
          <p className="text-muted-foreground">Templates tab — coming next</p>
        )}
      </main>
    </div>
  );
}
