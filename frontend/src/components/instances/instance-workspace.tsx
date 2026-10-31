import { useState } from "react";
import { ChevronLeft } from "lucide-react";
import { InstanceGrid } from "./instance-grid";
import { InstanceDetailPane } from "./instance-detail-pane";
import { WorkstationList, WorkstationPreview } from "./workstation-list";
import { HomeTabs } from "@/components/home/home-tabs";
import { AppsGrid } from "@/components/home/apps-grid";
import type { Workstation } from "@/api/client";
import { cn } from "@/lib/utils";

interface InstanceWorkspaceProps {
  onLaunch: () => void;
  onOpenSettings?: () => void;
}

export function InstanceWorkspace({ onLaunch, onOpenSettings }: InstanceWorkspaceProps) {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [selectedWs, setSelectedWs] = useState<Workstation | null>(null);
  const hasSel = selectedId !== null || selectedWs !== null;
  const clear = () => { setSelectedId(null); setSelectedWs(null); };

  return (
    <HomeTabs
      apps={<AppsGrid onOpenSettings={onOpenSettings} />}
      workspaces={
        <div className="relative flex h-full gap-3">
          {/* List pane: 40% on md+, full-width on narrow */}
          <div className="-m-1 w-full overflow-y-auto p-1 md:w-2/5 md:min-w-[320px]">
            <WorkstationList
              selectedId={selectedWs?.id}
              onSelect={(ws) => { setSelectedId(null); setSelectedWs(ws); }}
            />
            <h3 className="mb-2 text-sm font-medium text-muted-foreground">Instances</h3>
            <InstanceGrid
              dense
              selectedId={selectedId ?? undefined}
              onSelect={(i) => { setSelectedWs(null); setSelectedId(i.id); }}
              onLaunch={onLaunch}
            />
          </div>

          {/* Detail pane: inline on md+, overlay on narrow */}
          <div
            className={cn(
              "overflow-y-auto rounded-lg border border-border bg-card md:block md:w-3/5",
              hasSel ? "fixed inset-0 z-40 m-2 md:static md:m-0" : "hidden md:block"
            )}
          >
            {/* Back button for narrow screens */}
            {hasSel && (
              <button
                className="m-2 inline-flex min-h-11 items-center gap-1 text-sm text-muted-foreground hover:text-foreground transition-colors md:hidden"
                onClick={clear}
              >
                <ChevronLeft className="size-4" aria-hidden />Back
              </button>
            )}
            {selectedWs ? (
              <WorkstationPreview key={selectedWs.id} ws={selectedWs} />
            ) : (
              <InstanceDetailPane key={selectedId} instanceId={selectedId} />
            )}
          </div>
        </div>
      }
    />
  );
}
