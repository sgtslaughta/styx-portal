import { useState } from "react";
import { Header } from "@/components/layout/header";
import { TabNav } from "@/components/layout/tab-nav";
import { InstanceGrid } from "@/components/instances/instance-grid";
import { TemplateGrid } from "@/components/templates/template-grid";
import { RegistryBrowser } from "@/components/templates/registry-browser";
import { LaunchModal } from "@/components/templates/launch-modal";
import { InstanceDetail } from "@/components/instances/instance-detail";
import { MetricsDashboard } from "@/components/system/metrics-dashboard";
import { TooltipProvider } from "@/components/ui/tooltip";
import { useTemplates } from "@/hooks/use-templates";
import { cn } from "@/lib/utils";
import type { Instance, ServiceTemplate, RegistryImage } from "@/lib/types";

export default function App() {
  const { data: templates } = useTemplates();
  const [activeTab, setActiveTab] = useState("instances");
  const [templateSubTab, setTemplateSubTab] = useState<string | null>(null);
  const [selectedInstance, setSelectedInstance] = useState<Instance | null>(null);
  const [launchRegistry, setLaunchRegistry] = useState<RegistryImage | null>(null);
  const [launchTemplate, setLaunchTemplate] = useState<ServiceTemplate | null>(null);
  const [launchOpen, setLaunchOpen] = useState(false);

  function handleImportRegistry(image: RegistryImage) {
    setLaunchRegistry(image);
    setLaunchTemplate(null);
    setLaunchOpen(true);
  }

  function handleLaunchTemplate(template: ServiceTemplate) {
    setLaunchTemplate(template);
    setLaunchRegistry(null);
    setLaunchOpen(true);
  }

  function closeLaunchModal() {
    setLaunchOpen(false);
    setLaunchRegistry(null);
    setLaunchTemplate(null);
  }

  const resolvedSubTab = templateSubTab ?? (templates?.length ? "my-templates" : "registry");

  return (
    <TooltipProvider>
    <div className="flex min-h-screen flex-col bg-background">
      <Header />
      <TabNav activeTab={activeTab} onTabChange={setActiveTab} />
      <main className="flex-1 p-6">
        <div className={activeTab === "instances" ? "" : "hidden"}>
          <InstanceGrid onSelect={setSelectedInstance} onLaunch={() => setActiveTab("templates")} />
        </div>
        <div className={activeTab === "templates" ? "" : "hidden"}>
          <div className="mb-4 flex gap-1">
            {[
              { id: "registry", label: "LinuxServer Registry" },
              { id: "my-templates", label: "My Templates" },
            ].map((tab) => (
              <button key={tab.id} onClick={() => setTemplateSubTab(tab.id)} className={cn("rounded-lg px-3 py-1.5 text-sm font-medium transition-colors", resolvedSubTab === tab.id ? "bg-secondary text-foreground" : "text-muted-foreground hover:text-foreground")}>
                {tab.label}
              </button>
            ))}
          </div>
          <div className={resolvedSubTab === "registry" ? "" : "hidden"}>
            <RegistryBrowser onImport={handleImportRegistry} />
          </div>
          <div className={resolvedSubTab === "my-templates" ? "" : "hidden"}>
            <TemplateGrid onLaunch={handleLaunchTemplate} />
          </div>
        </div>
        <div className={activeTab === "system" ? "" : "hidden"}>
          <div className="mx-auto max-w-5xl">
            <MetricsDashboard />
          </div>
        </div>
      </main>
      <LaunchModal
        key={launchRegistry?.name ?? launchTemplate?.id ?? "custom"}
        open={launchOpen}
        onClose={closeLaunchModal}
        registryImage={launchRegistry}
        template={launchTemplate}
      />
      <InstanceDetail instance={selectedInstance} onClose={() => setSelectedInstance(null)} />
    </div>
    </TooltipProvider>
  );
}
