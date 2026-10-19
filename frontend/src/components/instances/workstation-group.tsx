import { useMemo, useState } from "react";
import type { Workstation } from "@/api/client";
import { WorkstationIcon } from "@/components/system/workstation-icon";
import { useAuth } from "@/hooks/use-auth";
import { useMyWorkstations } from "@/hooks/use-workstations";
import { useWorkstationConnect } from "@/hooks/use-workstation-connect";
import { wsDot, wsLine, type Selection } from "@/lib/workspace";
import { EmptyLine, GroupHeader, WorkspaceRow, useCollapsed } from "./workspace-row";

type SortKey = "status" | "name" | "seen";
const rank = (ws: Workstation) => (ws.status !== "online" ? 2 : ws.in_use ? 1 : 0);
const LIST_ID = "home-workstations";

export function WorkstationGroup({ query, selection, onSelect, onOpenSettings }: {
  query: string; selection: Selection | null; onSelect: (s: Selection) => void; onOpenSettings?: (section?: string) => void;
}) {
  const { data } = useMyWorkstations();
  const { user } = useAuth();
  const [collapsed, toggle] = useCollapsed("workstations");
  const [sort, setSort] = useState<SortKey>("status");
  const { connect, dialog, error } = useWorkstationConnect();

  const rows = useMemo(() => {
    const q = query.trim().toLowerCase();
    return (data ?? [])
      .filter((ws) => !q || `${ws.name} ${ws.hostname}`.toLowerCase().includes(q))
      .sort((a, b) =>
        sort === "name" ? a.name.localeCompare(b.name)
          : sort === "seen" ? (b.last_heartbeat ?? "").localeCompare(a.last_heartbeat ?? "")
          : rank(a) - rank(b) || a.name.localeCompare(b.name));
  }, [data, query, sort]);

  if (!data) return null;
  const isAdmin = user?.role === "admin";

  return (
    <section aria-label="Workstations">
      <GroupHeader title="Workstations" count={data.length} collapsed={collapsed} onToggle={toggle} controlsId={LIST_ID}>
        <select aria-label="Sort workstations" value={sort} onChange={(e) => setSort(e.target.value as SortKey)}
          className="h-8 rounded-md border border-border bg-background px-1.5 text-xs max-sm:h-11">
          <option value="status">Status</option>
          <option value="name">Name</option>
          <option value="seen">Last seen</option>
        </select>
      </GroupHeader>
      {!collapsed && (
        <div id={LIST_ID} className="py-1">
          {error && <p role="alert" className="px-2 text-xs text-destructive">{error}</p>}
          {data.length === 0 ? (
            <EmptyLine
              text={isAdmin ? "No workstations yet." : "No workstations shared with you yet."}
              action={isAdmin && onOpenSettings ? { label: "Add a workstation", onClick: () => onOpenSettings("workstations") } : undefined}
            />
          ) : rows.length === 0 ? (
            <p className="px-2 py-2 text-xs text-muted-foreground">No workstations match.</p>
          ) : (
            <ul className="space-y-0.5">
              {rows.map((ws) => (
                <WorkspaceRow
                  key={ws.id}
                  icon={<WorkstationIcon ws={ws} className="size-8" />}
                  name={ws.name}
                  line={wsLine(ws)}
                  dot={wsDot(ws)}
                  dim={ws.status !== "online"}
                  selected={selection?.kind === "workstation" && selection.id === ws.id}
                  onSelect={() => onSelect({ kind: "workstation", id: ws.id })}
                  quick={ws.status === "online" ? { label: `Connect to ${ws.name}`, onClick: () => connect(ws) } : undefined}
                />
              ))}
            </ul>
          )}
        </div>
      )}
      {dialog}
    </section>
  );
}
