import type { Workstation } from "@/api/client";
import {
  CODECS, CODEC_LABEL, DEFAULT_ENCODER, DEFAULT_FPS, TRANSPORT_LABEL, current, setField, type Field, type WsEdits,
} from "./streaming-overrides";

type Props = { workstations: Workstation[]; edits: WsEdits; transport: string; disabled: boolean; onEdits: (e: WsEdits) => void };

function live(ws: Workstation) {
  if (ws.in_use) return <><span className="sdot use" />Streaming{ws.in_use_by ? `, ${ws.in_use_by}` : ""}</>;
  if (ws.status === "online") return <><span className="sdot ok" />Idle</>;
  return <><span className="sdot" />{ws.status === "offline" ? "Offline" : ws.status.charAt(0).toUpperCase() + ws.status.slice(1)}</>;
}

export function StreamingWsTable({ workstations, edits, transport, disabled, onEdits }: Props) {
  if (workstations.length === 0) return <p className="text-sm text-muted-foreground">No workstations enrolled yet.</p>;
  return (
    <table className="dense full ws-table">
      <thead><tr><th>Workstation</th><th>Connection</th><th>Codec</th><th>Frame rate</th><th>Max bitrate</th><th>Streaming now</th></tr></thead>
      <tbody>
        {workstations.map((ws) => {
          const val = (f: Field) => current(ws, edits, f);
          const set = (f: Field, v: string) => onEdits(setField(edits, ws, f, v));
          const gpu = (ws.gpu_info as Record<string, unknown>)?.name;
          const mbps = val("bitrate_kbps") === "" ? "" : String(+(Number(val("bitrate_kbps")) / 1000).toFixed(3));
          return (
            <tr key={ws.id}>
              <td><strong>{ws.name}</strong>{typeof gpu === "string" && <small>{gpu}</small>}</td>
              <td>
                <select aria-label={`${ws.name} connection`} className={val("transport") ? "override" : undefined} disabled={disabled}
                  value={val("transport")} onChange={(e) => set("transport", e.target.value)}>
                  <option value="">Default ({TRANSPORT_LABEL[transport] ?? transport})</option>
                  <option value="websockets">WebSockets</option>
                  <option value="webrtc">WebRTC</option>
                </select>
              </td>
              <td>
                <select aria-label={`${ws.name} codec`} className={val("encoder") ? "override" : undefined} disabled={disabled}
                  value={val("encoder")} onChange={(e) => set("encoder", e.target.value)}>
                  <option value="">Default ({CODEC_LABEL[DEFAULT_ENCODER]})</option>
                  {CODECS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                </select>
              </td>
              <td>
                <select aria-label={`${ws.name} frame rate`} className={val("framerate") ? "override" : undefined} disabled={disabled}
                  value={val("framerate")} onChange={(e) => set("framerate", e.target.value)}>
                  <option value="">Default ({DEFAULT_FPS})</option>
                  {[30, 120].map((f) => <option key={f} value={String(f)}>{f}</option>)}
                </select>
              </td>
              <td>
                <span className={`in sm${val("bitrate_kbps") ? " override" : ""}`}>
                  <input type="number" min={1} aria-label={`${ws.name} max bitrate`} placeholder="Default" disabled={disabled} value={mbps}
                    onChange={(e) => set("bitrate_kbps", e.target.value === "" ? "" : String(Math.round(Number(e.target.value) * 1000)))} />
                  <em>Mbps</em>
                </span>
              </td>
              <td className="text-muted-foreground">{live(ws)}</td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
