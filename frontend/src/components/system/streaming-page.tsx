import "@/styles/streaming.css";
import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { api, type Setting, type SettingValue } from "@/api/client";
import { SettingField, isChanged } from "@/components/settings/setting-field";
import { SavePill } from "@/components/settings/save-pill";
import { Seg } from "@/components/settings/seg";
import { useUnsaved } from "@/components/settings/unsaved-context";
import { StreamingTurn } from "./streaming-turn";
import { StreamingWsTable } from "./streaming-ws-table";
import { editCount, mergedSettings, type WsEdits } from "./streaming-overrides";

const TRANSPORTS = [["websockets", "WebSockets"], ["webrtc", "WebRTC"]] as const;
const CODEC_OPTS = [["auto", "Auto"], ["av1", "AV1"], ["hevc", "HEVC"], ["h264", "H.264"]] as const;
const FPS_OPTS = [30, 60, 120];
const AFTER_SEGS = ["WORKSTATION_DEFAULT_BITRATE_KBPS", "WORKSTATION_DEFAULT_CRF", "WORKSTATION_DEFAULT_PAINT_OVER",
  "WORKSTATION_DEFAULT_STREAMING_MODE", "WORKSTATION_DEFAULT_FULLCOLOR", "WEBRTC_MAX_SESSION_H"];

/** One batch: system defaults (PATCH /system-settings) + per-workstation overrides, saved together. */
export function StreamingPage() {
  const qc = useQueryClient();
  const { setCount } = useUnsaved();
  const { data: groups = [], isLoading } = useQuery({ queryKey: ["system-settings"], queryFn: api.getSystemSettings });
  const { data: workstations = [] } = useQuery({ queryKey: ["workstations"], queryFn: api.listWorkstations, refetchInterval: 30000 });
  const [edits, setEdits] = useState<Record<string, SettingValue>>({});
  const [wsEdits, setWsEdits] = useState<WsEdits>({});

  const all = groups.filter((g) => g.group === "webrtc").flatMap((g) => g.settings);
  const byKey = Object.fromEntries(all.map((s) => [s.key, s])) as Record<string, Setting>;
  const changed = all.filter((s) => isChanged(s, edits[s.key]));
  const dirty = changed.length + editCount(wsEdits);
  useEffect(() => setCount(dirty), [dirty, setCount]);
  useEffect(() => () => setCount(0), [setCount]);

  const save = useMutation({
    mutationFn: async () => {
      const changes = Object.fromEntries(changed.map((s) => [s.key, edits[s.key] ?? ""])) as Record<string, number | boolean | string>;
      if (changed.length) {
        await api.updateSystemSettings(changes);
        setEdits({});
      }
      for (const [id, mine] of Object.entries(wsEdits)) {
        const ws = workstations.find((w) => w.id === id);
        if (!ws) continue;
        try {
          await api.updateWorkstation(id, { stream_settings: mergedSettings(ws, mine) });
        } catch (e) {
          throw new Error(`Could not save ${ws.name}: ${(e as Error).message}. Other changes were kept.`);
        }
        setWsEdits((p) => { const n = { ...p }; delete n[id]; return n; });
      }
    },
    onSuccess: async () => {
      await Promise.all([qc.invalidateQueries({ queryKey: ["system-settings"] }), qc.invalidateQueries({ queryKey: ["workstations"] })]);
      toast.success("Streaming settings saved");
    },
    onError: async (e: Error) => {
      toast.error(e.message);
      await Promise.all([qc.invalidateQueries({ queryKey: ["system-settings"] }), qc.invalidateQueries({ queryKey: ["workstations"] })]);
    },
  });

  if (isLoading) return <div className="text-sm text-muted-foreground">Loading settings...</div>;

  const stage = (k: string, v: SettingValue) => setEdits((p) => ({ ...p, [k]: v }));
  const drop = (k: string) => setEdits((p) => { const n = { ...p }; delete n[k]; return n; });
  const val = (k: string) => (edits[k] ?? byKey[k]?.value) as string;
  const field = (k: string) => {
    const s = byKey[k];
    return s && (
      <SettingField key={k} setting={s} value={edits[k]} disabled={save.isPending}
        onChange={(v) => stage(k, s.type === "int" && v !== "" ? Number(v) : v)} onRestore={() => drop(k)}
        onClear={() => stage(k, null)} onResetDefault={() => drop(k)} />
    );
  };
  const transport = val("WORKSTATION_TRANSPORT") ?? "websockets";
  const encoder = val("WORKSTATION_DEFAULT_ENCODER") ?? "auto";
  const fps = Number(val("WORKSTATION_DEFAULT_FRAMERATE") ?? 60);
  const chg = (k: string) => (byKey[k] && isChanged(byKey[k], edits[k]) ? " changed" : "");
  const fpsOpts = [...new Set([...FPS_OPTS, fps])].sort((a, b) => a - b).map((n) => [String(n), String(n)] as const);

  return (
    <>
      <div className="sec-head"><h2 className="ph">Streaming</h2><span className="rule" /><small>Viewers can still adjust quality from the stream panel</small></div>
      <div className="groups">
        <fieldset className="grp">
          <legend>Defaults for every workstation</legend>
          <div className={`row wide${isChanged(byKey.WORKSTATION_TRANSPORT as Setting, edits.WORKSTATION_TRANSPORT) ? " changed" : ""}`}>
            <span>Connection</span>
            <Seg label="Connection" value={transport as "webrtc"} options={TRANSPORTS} disabled={save.isPending} onChange={(v) => stage("WORKSTATION_TRANSPORT", v)} />
          </div>
          {byKey.WORKSTATION_DEFAULT_ENCODER && (
            <div className={`row wide${chg("WORKSTATION_DEFAULT_ENCODER")}`}><span>Codec</span>
              <Seg label="Codec" value={encoder as "auto"} options={CODEC_OPTS} disabled={save.isPending} onChange={(v) => stage("WORKSTATION_DEFAULT_ENCODER", v)} /></div>
          )}
          {byKey.WORKSTATION_DEFAULT_FRAMERATE && (
            <div className={`row wide${chg("WORKSTATION_DEFAULT_FRAMERATE")}`}><span>Frame rate</span>
              <Seg label="Frame rate" value={String(fps)} options={fpsOpts} disabled={save.isPending} onChange={(v) => stage("WORKSTATION_DEFAULT_FRAMERATE", Number(v))} /></div>
          )}
          {AFTER_SEGS.map(field)}
        </fieldset>
        <StreamingTurn provider={val("WEBRTC_TURN_PROVIDER") ?? "none"} byKey={byKey} edits={edits} disabled={save.isPending}
          onProvider={(v) => stage("WEBRTC_TURN_PROVIDER", v)} onToken={(v) => stage("CLOUDFLARE_TURN_API_TOKEN", v)} field={field} />
      </div>
      <div className="sec-head" style={{ marginTop: 26 }}><h2>Per workstation</h2><span className="rule" /><small>Gold values override the defaults</small></div>
      <StreamingWsTable workstations={workstations} edits={wsEdits} defaults={{ transport, encoder, framerate: fps }} disabled={save.isPending} onEdits={setWsEdits} />
      <SavePill count={dirty} saving={save.isPending} onSave={() => save.mutate()} onDiscard={() => { setEdits({}); setWsEdits({}); }} />
    </>
  );
}
