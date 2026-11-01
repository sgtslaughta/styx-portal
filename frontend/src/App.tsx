import { useEffect, useState } from "react";
import { toast } from "sonner";
import { AlertTriangle } from "lucide-react";
import { Header, type HeaderTab } from "@/components/layout/header";
import { StatusRail } from "@/components/layout/status-rail";
import { HomePage } from "@/components/home/home-page";
import { NewContainerDrawer } from "@/components/launch/new-container-drawer";
import { SettingsLayout } from "@/components/settings/settings-layout";
import { TooltipProvider } from "@/components/ui/tooltip";
import { useAuth } from "@/hooks/use-auth";
import { AdminActiveContext } from "@/hooks/use-admin-poll";

export default function App() {
  const { user } = useAuth();
  const [activeTab, setActiveTab] = useState<HeaderTab>("home");
  const [launchOpen, setLaunchOpen] = useState(false);
  const [railPad, setRailPad] = useState(0);

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

  return (
    <TooltipProvider>
    <div className="flex h-dvh flex-col bg-background styx-app-bg">
      <Header activeTab={activeTab} onTabChange={setActiveTab} />
      <main className="min-h-0 flex-1 overflow-y-auto p-6 transition-[padding] motion-reduce:transition-none" style={{ paddingRight: 24 + railPad }}>
        <div className={activeTab === "home" ? "" : "hidden"}>
          <HomePage onNewContainer={() => setLaunchOpen(true)} onOpenSettings={() => setActiveTab("admin")} />
        </div>
        <div className={activeTab === "admin" ? "" : "hidden"}>
          <AdminActiveContext.Provider value={activeTab === "admin"}><SettingsLayout /></AdminActiveContext.Provider>
        </div>
      </main>
      <StatusRail forceCollapsed={activeTab === "admin"} onOpenAdmin={() => setActiveTab("admin")} onWidthChange={setRailPad} />
      <NewContainerDrawer open={launchOpen} onClose={() => setLaunchOpen(false)} />
    </div>
    </TooltipProvider>
  );
}
