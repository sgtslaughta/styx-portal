import { useState } from "react";
import { ChevronLeft } from "lucide-react";
import { InstanceDetailPane } from "./instance-detail-pane";
import { WorkspaceList } from "./workspace-list";
import type { Selection } from "@/lib/workspace";
import { cn } from "@/lib/utils";

interface InstanceWorkspaceProps {
  onLaunch: () => void;
  onOpenSettings?: (section?: string) => void;
}

export function InstanceWorkspace({ onLaunch, onOpenSettings }: InstanceWorkspaceProps) {
  const [sel, setSel] = useState<Selection | null>(null);
  const instanceId = sel?.kind === "instance" ? sel.id : null; // the workstation pane lands in Task 7

  return (
    <div className="relative flex h-full gap-3">
      <div className="h-full w-full md:w-2/5 md:min-w-[320px]">
        <WorkspaceList selection={sel} onSelect={setSel} onLaunch={onLaunch} onOpenSettings={onOpenSettings} />
      </div>
      <div className={cn("overflow-y-auto rounded-lg border border-border bg-card md:block md:w-3/5",
        instanceId ? "fixed inset-0 z-40 m-2 md:static md:m-0" : "hidden md:block")}>
        {instanceId && (
          <button className="m-2 inline-flex min-h-11 items-center gap-1 text-sm text-muted-foreground transition-colors hover:text-foreground md:hidden"
            onClick={() => setSel(null)}>
            <ChevronLeft className="size-4" aria-hidden />Back
          </button>
        )}
        <InstanceDetailPane key={instanceId} instanceId={instanceId} />
      </div>
    </div>
  );
}
