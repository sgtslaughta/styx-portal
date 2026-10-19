import { useState } from "react";
import { ChevronLeft, Monitor, Rocket } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/hooks/use-auth";
import { useInstances } from "@/hooks/use-instances";
import { useMyWorkstations } from "@/hooks/use-workstations";
import { readRecent, type Selection } from "@/lib/workspace";
import { cn } from "@/lib/utils";
import { InstanceDetailPane } from "./instance-detail-pane";
import { WorkstationDetailPane } from "./workstation-detail-pane";
import { WorkspaceList } from "./workspace-list";

interface InstanceWorkspaceProps {
  onLaunch: () => void;
  onOpenSettings?: (section?: string) => void;
}

function GuideCard({ isAdmin, onLaunch, onOpenSettings }: { isAdmin: boolean } & InstanceWorkspaceProps) {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-3 p-6 text-center">
      <p className="text-sm text-muted-foreground">Pick a workspace on the left to see it here.</p>
      <div className="flex flex-wrap justify-center gap-2">
        {isAdmin && onOpenSettings && (
          <Button size="sm" variant="outline" onClick={() => onOpenSettings("workstations")}><Monitor aria-hidden />Add a workstation</Button>
        )}
        <Button size="sm" onClick={onLaunch}><Rocket aria-hidden />Launch an instance</Button>
      </div>
    </div>
  );
}

export function InstanceWorkspace({ onLaunch, onOpenSettings }: InstanceWorkspaceProps) {
  const [sel, setSel] = useState<Selection | null>(null);
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";
  const { data: workstations } = useMyWorkstations();
  const { data: instances } = useInstances();
  // Nothing picked: show the workspace last opened in this browser, if it still exists.
  const shown = sel ?? readRecent();
  const ws = shown?.kind === "workstation" ? workstations?.find((w) => w.id === shown.id) : undefined;
  const inst = shown?.kind === "instance" ? instances?.find((i) => i.id === shown.id) : undefined;

  return (
    <div className="relative flex h-full gap-3">
      <div className="h-full w-full md:w-2/5 md:min-w-[320px]">
        <WorkspaceList selection={shown} onSelect={setSel} onLaunch={onLaunch} onOpenSettings={onOpenSettings} />
      </div>
      {/* Detail pane: inline on md+, overlay with Back on narrow screens (only for an explicit pick). */}
      <div className={cn("overflow-y-auto rounded-lg border border-border bg-card md:block md:w-3/5",
        sel ? "fixed inset-0 z-40 m-2 md:static md:m-0" : "hidden md:block")}>
        {sel && (
          <button className="m-2 inline-flex min-h-11 items-center gap-1 text-sm text-muted-foreground transition-colors hover:text-foreground md:hidden"
            onClick={() => setSel(null)}>
            <ChevronLeft className="size-4" aria-hidden />Back
          </button>
        )}
        {ws ? <WorkstationDetailPane key={ws.id} ws={ws} />
          : inst ? <InstanceDetailPane key={inst.id} instanceId={inst.id} />
          : <GuideCard isAdmin={isAdmin} onLaunch={onLaunch} onOpenSettings={onOpenSettings} />}
      </div>
    </div>
  );
}
