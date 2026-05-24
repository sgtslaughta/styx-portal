import { useState } from "react";
import { Header } from "@/components/layout/header";
import { TabNav } from "@/components/layout/tab-nav";
import { InstanceGrid } from "@/components/instances/instance-grid";
import { TemplateGrid } from "@/components/templates/template-grid";
import { RegistryBrowser } from "@/components/templates/registry-browser";
import { LaunchModal } from "@/components/templates/launch-modal";
import { cn } from "@/lib/utils";
import type { Instance, ServiceTemplate, RegistryImage } from "@/lib/types";

export default function App() {
  const [activeTab, setActiveTab] = useState("instances");
  const [templateSubTab, setTemplateSubTab] = useState("registry");
  const [_selectedInstance, setSelectedInstance] = useState<Instance | null>(null);
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
    setActiveTab("instances");
  }

  return (
    <div className="flex min-h-screen flex-col bg-background">
      <Header />
      <TabNav activeTab={activeTab} onTabChange={setActiveTab} />
      <main className="flex-1 p-6">
        {activeTab === "instances" && (
          <InstanceGrid onSelect={setSelectedInstance} onLaunch={() => setActiveTab("templates")} />
        )}
        {activeTab === "templates" && (
          <div>
            <div className="mb-4 flex gap-1">
              {[
                { id: "registry", label: "LinuxServer Registry" },
                { id: "my-templates", label: "My Templates" },
              ].map((tab) => (
                <button key={tab.id} onClick={() => setTemplateSubTab(tab.id)} className={cn("rounded-lg px-3 py-1.5 text-sm font-medium transition-colors", templateSubTab === tab.id ? "bg-secondary text-foreground" : "text-muted-foreground hover:text-foreground")}>
                  {tab.label}
                </button>
              ))}
            </div>
            {templateSubTab === "registry" && <RegistryBrowser onImport={handleImportRegistry} />}
            {templateSubTab === "my-templates" && <TemplateGrid onLaunch={handleLaunchTemplate} />}
          </div>
        )}
      </main>
      <LaunchModal open={launchOpen} onClose={closeLaunchModal} registryImage={launchRegistry} template={launchTemplate} />
    </div>
  );
}
