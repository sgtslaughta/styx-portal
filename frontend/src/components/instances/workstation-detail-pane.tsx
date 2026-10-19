import { AlertTriangle, ExternalLink } from "lucide-react";
import type { Workstation } from "@/api/client";
import { Button } from "@/components/ui/button";
import { WorkstationIcon } from "@/components/system/workstation-icon";
import { useWorkstationConnect } from "@/hooks/use-workstation-connect";
import { osName, since, wsDot } from "@/lib/workspace";
import { PaneHeader } from "./pane-header";

function facts(ws: Workstation): [string, string][] {
  const gpu = ws.gpu_info as Record<string, unknown>;
  return [
    ["System", osName(ws)],
    ["GPU", String(gpu.model || gpu.vendor || "None detected")],
    ["Display", ws.display_server || "—"],
    ["Agent", ws.agent_version ? `v${ws.agent_version}${ws.agent_outdated ? " · update available" : ""}` : "—"],
  ];
}

/** Rich workstation card (no image yet: the last-frame preview waits for the agent batch). */
export function WorkstationDetailPane({ ws }: { ws: Workstation }) {
  const { connect, dialog, error } = useWorkstationConnect();
  const online = ws.status === "online";
  const other = online && ws.in_use && !ws.in_use_self;
  const seen = since(ws.last_heartbeat);
  const dot = wsDot(ws);

  const actions = (
    <div className="flex flex-wrap gap-2">
      {online && (
        <Button variant="ghost" onClick={() => connect(ws, "new_tab")}><ExternalLink aria-hidden />Open in new tab</Button>
      )}
      {!online ? (
        <Button disabled>Offline</Button>
      ) : other ? (
        <Button onClick={() => connect(ws)}>Join</Button>
      ) : (
        <Button onClick={() => connect(ws)}>{ws.in_use_self ? "Reconnect" : "Connect"}</Button>
      )}
    </div>
  );

  return (
    <div className="flex h-full flex-col overflow-y-auto">
      <PaneHeader icon={<WorkstationIcon ws={ws} className="size-20 rounded-xl" />} title={ws.name}
        status={dot.label} dotClass={dot.dotClass} muted={!online} actions={actions} />
      <div className="space-y-4 p-4">
        {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
        <dl className="grid grid-cols-2 gap-3 text-sm max-sm:grid-cols-1">
          {facts(ws).map(([k, v]) => (
            <div key={k} className="rounded-lg border border-border bg-card/50 p-3">
              <dt className="text-xs text-muted-foreground">{k}</dt>
              <dd className="truncate font-medium" title={v}>{v}</dd>
            </div>
          ))}
        </dl>
        {ws.last_error && (
          <div role="status" className="flex gap-2 rounded-md border border-warning/40 bg-warning/10 p-3 text-xs">
            <AlertTriangle className="mt-px size-4 shrink-0 text-warning" aria-hidden />
            <span>{ws.last_error}</span>
          </div>
        )}
        {(seen || !online) && (
          <p className="text-xs text-muted-foreground">
            {online ? `seen ${seen} ago` : seen ? `Offline · last seen ${seen} ago` : "Offline · never seen"}
          </p>
        )}
      </div>
      {dialog}
    </div>
  );
}
