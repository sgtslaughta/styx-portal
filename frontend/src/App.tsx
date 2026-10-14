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
import { useAuth } from "@/hooks/use-auth";
import { useTemplates } from "@/hooks/use-templates";
import { cn } from "@/lib/utils";
import type { ServiceTemplate, RegistryImage } from "@/lib/types";

export default function App() {
  const { data: templates } = useTemplates();
  const { user } = useAuth();
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

  // /?setup=<id> (tile or shell card of an unconfigured service): admins land on Settings > Services.
  useEffect(() => {
    if (user?.role === "admin" && new URLSearchParams(window.location.search).has("setup")) setActiveTab("system");
  }, [user?.role]);

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
    <div className="flex h-dvh flex-col bg-background styx-app-bg">
      <Header />
      <TabNav activeTab={activeTab} onTabChange={setActiveTab} />
      <main className="min-h-0 flex-1 overflow-y-auto p-6">
        <div className={activeTab === "instances" ? "h-full" : "hidden"}>
          <InstanceWorkspace onLaunch={() => setActiveTab("templates")} onOpenSettings={() => setActiveTab("system")} />
        </div>
        <div className={activeTab === "templates" ? "" : "hidden"}>
          <div className="mb-4 flex gap-1">
            {[
              { id: "registry", label: "LinuxServer registry" },
              { id: "my-templates", label: "My templates" },
            ].map((tab) => (
              <button key={tab.id} onClick={() => setTemplateSubTab(tab.id)} aria-current={resolvedSubTab === tab.id ? "page" : undefined} className={cn("rounded-lg px-3 py-1.5 text-sm font-medium transition-colors outline-none focus-visible:ring-2 focus-visible:ring-ring max-sm:min-h-11", resolvedSubTab === tab.id ? "bg-secondary text-foreground" : "text-muted-foreground hover:text-foreground")}>
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
