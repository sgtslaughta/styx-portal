import { useState } from "react";
import { InstanceGrid } from "./instance-grid";
import { InstanceDetailPane } from "./instance-detail-pane";
import { WorkstationGrid } from "./workstation-grid";
import { cn } from "@/lib/utils";

interface InstanceWorkspaceProps {
  onLaunch: () => void;
}

export function InstanceWorkspace({ onLaunch }: InstanceWorkspaceProps) {
  const [selectedId, setSelectedId] = useState<string | null>(null);

  return (
    <div className="relative flex h-[calc(100vh-8.5rem)] gap-3">
      {/* List pane: 40% on md+, full-width on narrow */}
      <div className="w-full overflow-y-auto md:w-2/5 md:min-w-[320px]">
        <WorkstationGrid />
        <InstanceGrid
          dense
          selectedId={selectedId ?? undefined}
          onSelect={(i) => setSelectedId(i.id)}
          onLaunch={onLaunch}
        />
      </div>

      {/* Detail pane: inline on md+, overlay on narrow */}
      <div
        className={cn(
          "overflow-y-auto rounded-lg border border-border bg-card md:block md:w-3/5",
          selectedId ? "fixed inset-0 z-40 m-2 md:static md:m-0" : "hidden md:block"
        )}
      >
        {/* Back button for narrow screens */}
        {selectedId && (
          <button
            className="m-2 text-sm text-muted-foreground hover:text-foreground transition-colors md:hidden"
            onClick={() => setSelectedId(null)}
          >
            ← Back
          </button>
        )}
        <InstanceDetailPane key={selectedId} instanceId={selectedId} />
      </div>
    </div>
  );
}
