import { api, type Workstation } from "@/api/client";
import { Button } from "@/components/ui/button";
import { Thumbnail } from "@/components/common/thumbnail";
import { AgentUpdateChip } from "@/components/system/agent-update-chip";

const num = (v: unknown) => (typeof v === "number" && Number.isFinite(v) ? Math.round(v) : null);

/** Only real numbers: the API does not expose utilisation yet, so this shows an em dash. */
function Meter({ label, pct }: { label: string; pct: number | null }) {
  return (
    <div className="wsmeter">
      <div><span>{label}</span><b>{pct === null ? "—" : `${pct}%`}</b></div>
      <span className="track"><i style={{ width: `${pct ?? 0}%` }} /></span>
    </div>
  );
}

function statusLine(ws: Workstation) {
  const v = ws.agent_version ? `, agent ${ws.agent_version}` : "";
  if (ws.in_use) return { dot: "use", text: `${ws.in_use_by ?? "Someone"} connected${v}` };
  if (ws.status === "online") return { dot: "ok", text: `Online${v}` };
  return { dot: "", text: `${ws.status.charAt(0).toUpperCase()}${ws.status.slice(1)}${v}` };
}

type Props = {
  ws: Workstation;
  onManage: () => void;
  onUpdate: () => void;
  onManual: () => void;
};

export function WorkstationRow({ ws, onManage, onUpdate, onManual }: Props) {
  const st = statusLine(ws);
  const live = ws.status === "online";
  return (
    <div className="wsrow">
      <Thumbnail src={api.workstationThumbUrl(ws.id)} icon={null} isLive={live} small />
      <div>
        <strong>{ws.name}</strong>
        <small><span className={`sdot ${st.dot}`} />{st.text}</small>
        <AgentUpdateChip state={ws.update_state} error={ws.update_error} />
      </div>
      {live ? (
        <>
          <Meter label="GPU" pct={num(ws.gpu_info.utilization ?? ws.gpu_info.util_pct)} />
          <Meter label="Memory" pct={num(ws.os_info.mem_used_pct)} />
        </>
      ) : (
        <div className="text-[13px] text-muted-foreground">No data while {ws.status}</div>
      )}
      <div className="flex gap-2">
        {ws.agent_outdated && !["requested", "updating"].includes(ws.update_state ?? "") && (
          <Button onClick={onUpdate} size="sm">Update agent</Button>
        )}
        {ws.agent_outdated && (
          <Button onClick={onManual} variant="secondary" size="sm" title="Copy-paste one-liner">Manual</Button>
        )}
        <Button onClick={onManage} variant="ghost" size="sm">Manage</Button>
      </div>
    </div>
  );
}
