import { useEffect, useState } from "react";
import { toast } from "sonner";
import { AlertTriangle } from "lucide-react";
import { Header } from "@/components/layout/header";
import { TabNav } from "@/components/layout/tab-nav";
import { InstanceWorkspace } from "@/components/instances/instance-workspace";
import { TemplateGrid } from "@/components/templates/template-grid";
import { RegistryBrowser } from "@/components/templates/registry-browser";
import { LaunchModal } from "@/components/templates/launch-modal";
import { SettingsLayout } from "@/components/settings/settings-layout";
import { TooltipProvider } from "@/components/ui/tooltip";
import { useTemplates } from "@/hooks/use-templates";
import { cn } from "@/lib/utils";
import type { ServiceTemplate, RegistryImage } from "@/lib/types";

export default function App() {
  const { data: templates } = useTemplates();
  const [activeTab, setActiveTab] = useState("instances");
  const [templateSubTab, setTemplateSubTab] = useState<string | null>(null);
  const [launchRegistry, setLaunchRegistry] = useState<RegistryImage | null>(null);
  const [launchTemplate, setLaunchTemplate] = useState<ServiceTemplate | null>(null);
  const [launchOpen, setLaunchOpen] = useState(false);

  useEffect(() => {
    const sp = new URLSearchParams(window.location.search);
    const stopped = sp.get("stopped");
    if (stopped) {
      window.history.replaceState({}, "", window.location.pathname);
      // Defer so the toast fires after sonner's <Toaster> has mounted/subscribed
      // (this effect runs before the Toaster's subscribe effect, so an immediate
      // toast on mount is dropped).
      setTimeout(
        () =>
          toast.warning(`Instance "${stopped}" is stopped`, {
            icon: <AlertTriangle className="h-5 w-5 text-yellow-500" />,
            duration: 6000,
          }),
        0,
      );
    }
  }, []);

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
    <div className="flex min-h-screen flex-col bg-background styx-app-bg">
      <Header />
      <TabNav activeTab={activeTab} onTabChange={setActiveTab} />
      <main className="flex-1 p-6">
        <div className={activeTab === "instances" ? "" : "hidden"}>
          <InstanceWorkspace onLaunch={() => setActiveTab("templates")} />
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
            <TemplateGrid
              onLaunch={handleLaunchTemplate}
              onImportRegistry={() => setTemplateSubTab("registry")}
            />
          </div>
        </div>
        <div className={activeTab === "system" ? "" : "hidden"}>
          <SettingsLayout />
        </div>
      </main>
      <LaunchModal
        key={launchRegistry?.name ?? launchTemplate?.id ?? "custom"}
        open={launchOpen}
        onClose={closeLaunchModal}
        registryImage={launchRegistry}
        template={launchTemplate}
      />
    </div>
    </TooltipProvider>
  );
}
