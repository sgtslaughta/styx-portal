import { useState } from "react";
import { SearchSortBar } from "@/components/common/search-sort-bar";
import type { Selection } from "@/lib/workspace";
import { InstanceGroup } from "./instance-group";
import { WorkstationGroup } from "./workstation-group";

/** Left list: one search over both kinds, one scroll area, sticky group headers. */
export function WorkspaceList({ selection, onSelect, onLaunch, onOpenSettings }: {
  selection: Selection | null; onSelect: (s: Selection) => void; onLaunch: () => void; onOpenSettings?: (section?: string) => void;
}) {
  const [query, setQuery] = useState("");
  return (
    <div className="flex h-full min-h-0 flex-col gap-2">
      <SearchSortBar query={query} onQueryChange={setQuery} placeholder="Search workspaces…" />
      <div className="min-h-0 flex-1 overflow-y-auto pr-1">
        <WorkstationGroup query={query} selection={selection} onSelect={onSelect} onOpenSettings={onOpenSettings} />
        <InstanceGroup query={query} selection={selection} onSelect={onSelect} onLaunch={onLaunch} />
      </div>
    </div>
  );
}
