import { useState } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";
import { api, type Workstation } from "@/api/client";
import { Button } from "@/components/ui/button";

const FRAMERATES = [30, 60, 120];
const CODECS = [
  ["auto", "Auto (AV1 first)"],
  ["hevc", "HEVC"],
  ["av1", "AV1"],
  ["h264", "H.264"],
] as const;

export function WorkstationStreamSettings({
  ws,
  onSaved,
}: {
  ws: Workstation;
  onSaved: () => void;
}) {
  const ss = ws.stream_settings ?? {};
  const [open, setOpen] = useState(false);
  const [framerate, setFramerate] = useState<number>(
    Number(ss.framerate) || 60
  );
  const [encoder, setEncoder] = useState<string>(
    typeof ss.encoder === "string" ? ss.encoder : "auto"
  );
  const [crf, setCrf] = useState<string>(
    ss.h264_crf != null ? String(ss.h264_crf) : ""
  );
  const [gaming, setGaming] = useState<boolean>(
    ss.h264_streaming_mode === true
  );
  const [paintOver, setPaintOver] = useState<boolean>(
    ss.use_paint_over_quality !== false
  );
  const [fullColor, setFullColor] = useState<boolean>(
    ss.video_fullcolor === true
  );
  const [bitrate, setBitrate] = useState<string>(
    ss.bitrate_kbps != null ? String(ss.bitrate_kbps) : ""
  );
  const [transport, setTransport] = useState<string>(
    typeof ss.transport === "string" ? ss.transport : "inherit"
  );
  const [seatX11, setSeatX11] = useState<string>(
    ss.seat_x11 === "off" ? "off" : "auto"
  );
  const [saving, setSaving] = useState(false);

  const save = async () => {
    setSaving(true);
    const next: Record<string, unknown> = {
      ...ss,
      framerate,
      encoder,
      h264_streaming_mode: gaming,
      use_paint_over_quality: paintOver,
      video_fullcolor: fullColor,
      transport,
      seat_x11: seatX11,
    };
    const crfNum = parseInt(crf, 10);
    if (!Number.isNaN(crfNum) && crfNum >= 5 && crfNum <= 50) {
      next.h264_crf = crfNum;
    } else {
      delete next.h264_crf;
    }
    const brNum = parseInt(bitrate, 10);
    if (!Number.isNaN(brNum) && brNum >= 1000) {
      next.bitrate_kbps = brNum;
    } else {
      delete next.bitrate_kbps;
    }
    try {
      await api.updateWorkstation(ws.id, { stream_settings: next });
      onSaved();
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="text-sm">
      <button
        className="flex items-center gap-1 text-muted-foreground"
        onClick={() => setOpen(!open)}
      >
        {open ? (
          <ChevronDown className="h-3.5 w-3.5" />
        ) : (
          <ChevronRight className="h-3.5 w-3.5" />
        )}
        Stream settings
      </button>
      {open && (
        <div className="mt-2 flex flex-wrap items-center gap-4 rounded-md bg-muted/40 p-3">
          <label
            className="flex items-center gap-1.5"
            title="Default; viewers can change it from the stream panel."
          >
            FPS
            <select
              className="rounded border border-border bg-surface px-1 py-0.5"
              value={framerate}
              onChange={(e) => setFramerate(Number(e.target.value))}
            >
              {FRAMERATES.map((f) => (
                <option key={f} value={f}>
                  {f}
                </option>
              ))}
            </select>
          </label>
          <label
            className="flex items-center gap-1.5"
            title="WebRTC is lower latency; through restrictive networks it needs a TURN relay configured in Admin → Settings (billed per GB)."
          >
            Transport
            <select
              aria-label="Transport"
              className="rounded border border-border bg-surface px-1 py-0.5"
              value={transport}
              onChange={(e) => setTransport(e.target.value)}
            >
              <option value="inherit">Inherit (system default)</option>
              <option value="websockets">WebSockets</option>
              <option value="webrtc">WebRTC</option>
            </select>
          </label>
          <label
            className="flex items-center gap-1.5"
            title="Lets X11-only apps such as Steam run. Some GNOME 50 hosts deadlock with it; Auto detects that and turns it off on that host."
          >
            X11 apps (Xwayland)
            <select
              aria-label="X11 apps (Xwayland)"
              className="rounded border border-border bg-surface px-1 py-0.5"
              value={seatX11}
              onChange={(e) => setSeatX11(e.target.value)}
            >
              <option value="auto">Auto (falls back if the seat hangs)</option>
              <option value="off">Off</option>
            </select>
          </label>
          <span className="basis-full text-xs text-muted-foreground">
            Lets X11-only apps such as Steam run. Some GNOME 50 hosts deadlock
            with it; Auto detects that and turns it off on that host.
          </span>
          <label
            className="flex items-center gap-1.5"
            title="Preferred codec, if this GPU encodes it in hardware. Other hardware codecs stay as fallbacks for browsers that cannot decode it. Pick HEVC for viewers without AV1 hardware decode."
          >
            Codec
            <select
              className="rounded border border-border bg-surface px-1 py-0.5"
              value={encoder}
              onChange={(e) => setEncoder(e.target.value)}
            >
              {CODECS.map(([v, label]) => (
                <option key={v} value={v}>
                  {label}
                </option>
              ))}
            </select>
          </label>
          <label
            className="flex items-center gap-1.5"
            title="H.264 CRF 5-50; lower = higher quality/bitrate. Blank = default (25). Default; viewers can change it from the stream panel."
          >
            Quality (CRF)
            <input
              className="w-16 rounded border border-border bg-surface px-1 py-0.5"
              type="number"
              min={5}
              max={50}
              placeholder="25"
              value={crf}
              onChange={(e) => setCrf(e.target.value)}
            />
          </label>
          <label
            className="flex items-center gap-1.5"
            title="Viewers start here and can lower it from the stream panel."
          >
            Max bitrate (kbps)
            <input
              className="w-20 rounded border border-border bg-surface px-1 py-0.5"
              type="number"
              min={1000}
              placeholder="16000"
              value={bitrate}
              onChange={(e) => setBitrate(e.target.value)}
            />
          </label>
          <label
            className="flex items-center gap-1.5"
            title="Full-motion encoding: consistent latency in games; more bandwidth on a static desktop."
          >
            <input
              type="checkbox"
              checked={gaming}
              onChange={(e) => setGaming(e.target.checked)}
            />
            Gaming mode
          </label>
          <label
            className="flex items-center gap-1.5"
            title="Re-encode static screens at higher quality (crisp text when idle)."
          >
            <input
              type="checkbox"
              checked={paintOver}
              onChange={(e) => setPaintOver(e.target.checked)}
            />
            Sharpen static screen
          </label>
          <label
            className="flex items-center gap-1.5"
            title="4:4:4 chroma for crisp text. Warning: VA-API GPUs cannot encode H.264 4:4:4, so this switches to software x264 (more CPU, larger frames) and can make audio stutter on slow uplinks."
          >
            <input
              type="checkbox"
              checked={fullColor}
              onChange={(e) => setFullColor(e.target.checked)}
            />
            Full colour (4:4:4)
          </label>
          <Button size="sm" onClick={save} disabled={saving}>
            {saving ? "Saving…" : "Save"}
          </Button>
          <span className="text-xs text-muted-foreground">
            Applies when no one is connected to this workstation.
          </span>
        </div>
      )}
    </div>
  );
}
