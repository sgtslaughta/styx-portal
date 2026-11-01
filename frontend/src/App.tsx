import { useEffect, useState } from "react";
import { toast } from "sonner";
import { AlertTriangle } from "lucide-react";
import { Header, type HeaderTab } from "@/components/layout/header";
import { InstanceWorkspace } from "@/components/instances/instance-workspace";
import { LaunchModal } from "@/components/templates/launch-modal";
import { SettingsLayout } from "@/components/settings/settings-layout";
import { TooltipProvider } from "@/components/ui/tooltip";
import { useAuth } from "@/hooks/use-auth";
import type { ServiceTemplate, RegistryImage } from "@/lib/types";

export default function App() {
  const { user } = useAuth();
  const [activeTab, setActiveTab] = useState<HeaderTab>("home");
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
    if (user?.role === "admin" && new URLSearchParams(window.location.search).has("setup")) setActiveTab("admin");
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

  // Unreachable until Task 7 rewires launching; kept so LaunchModal flow stays intact.
  void [handleImportRegistry, handleLaunchTemplate];

  return (
    <TooltipProvider>
    <div className="flex h-dvh flex-col bg-background styx-app-bg">
      <Header activeTab={activeTab} onTabChange={setActiveTab} />
      <main className="min-h-0 flex-1 overflow-y-auto p-6">
        <div className={activeTab === "home" ? "h-full" : "hidden"}>
          <InstanceWorkspace onLaunch={() => {}} onOpenSettings={() => setActiveTab("admin")} />
        </div>
        <div className={activeTab === "admin" ? "" : "hidden"}>
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
