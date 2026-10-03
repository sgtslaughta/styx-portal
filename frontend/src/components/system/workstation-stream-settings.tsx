import { useState } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";
import { api, type Workstation } from "@/api/client";
import { Button } from "@/components/ui/button";

const FRAMERATES = [30, 60, 120];

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
  const [crf, setCrf] = useState<string>(
    ss.h264_crf != null ? String(ss.h264_crf) : ""
  );
  const [gaming, setGaming] = useState<boolean>(
    ss.h264_streaming_mode === true
  );
  const [paintOver, setPaintOver] = useState<boolean>(
    ss.use_paint_over_quality !== false
  );
  const [saving, setSaving] = useState(false);

  const save = async () => {
    setSaving(true);
    const next: Record<string, unknown> = {
      ...ss,
      framerate,
      h264_streaming_mode: gaming,
      use_paint_over_quality: paintOver,
    };
    const crfNum = parseInt(crf, 10);
    if (!Number.isNaN(crfNum) && crfNum >= 5 && crfNum <= 50) {
      next.h264_crf = crfNum;
    } else {
      delete next.h264_crf;
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
          <label className="flex items-center gap-1.5">
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
            title="H.264 CRF 5-50; lower = higher quality/bitrate. Blank = default (25)."
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
          <Button size="sm" onClick={save} disabled={saving}>
            {saving ? "Saving…" : "Save"}
          </Button>
          <span className="text-xs text-muted-foreground">
            Applying restarts the stream.
          </span>
        </div>
      )}
    </div>
  );
}
