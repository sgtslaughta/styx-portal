import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { api, type Workstation } from "@/api/client";
import { Button } from "@/components/ui/button";
import { WorkstationIcon } from "@/components/system/workstation-icon";
import { cn } from "@/lib/utils";

type Kind = Workstation["icon_kind"];
export const MAX_IMAGE_BYTES = 256 * 1024;
const MAX_EMOJI_BYTES = 16;
const MODES: { key: Kind; label: string }[] = [
  { key: "auto", label: "Auto" },
  { key: "emoji", label: "Emoji" },
  { key: "image", label: "Image" },
];

function graphemes(s: string): number {
  // Segmenter is missing from the configured TS lib and some older browsers; fall back to code points.
  const Seg = (Intl as unknown as { Segmenter?: new () => { segment(s: string): Iterable<unknown> } }).Segmenter;
  return Seg ? [...new Seg().segment(s)].length : [...s].length;
}

export function emojiError(s: string): string | null {
  if (!s) return "Enter an emoji.";
  if (graphemes(s) !== 1) return "Use a single emoji.";
  if (new TextEncoder().encode(s).length > MAX_EMOJI_BYTES) return "That emoji is too long. Try a simpler one.";
  return null;
}

export function WorkstationIconSettings({ ws, onSaved }: { ws: Workstation; onSaved: () => void }) {
  const [mode, setMode] = useState<Kind>(ws.icon_kind);
  const [emoji, setEmoji] = useState("");
  const [image, setImage] = useState<string | null>(null);
  const [fileError, setFileError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const pickId = useRef(0);
  const [fileKey, setFileKey] = useState(0);

  useEffect(() => {
    setMode(ws.icon_kind);
  }, [ws.icon_kind, ws.icon_etag]);

  const emojiErr = mode === "emoji" && emoji ? emojiError(emoji) : null;
  const canSave = !saving && (mode === "emoji" ? emojiError(emoji) === null : image !== null);

  const send = async (kind: Kind, value?: string) => {
    setSaving(true);
    try {
      await api.setWorkstationIcon(ws.id, kind, value);
      setEmoji("");
      setImage(null);
      setFileError(null);
      setFileKey((k) => k + 1);
      onSaved();
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setSaving(false);
    }
  };

  const reset = async () => {
    setMode("auto");
    await send("auto");
  };

  const pick = (file: File | undefined) => {
    const id = ++pickId.current;
    setFileError(null);
    setImage(null);
    if (!file) return;
    if (file.size > MAX_IMAGE_BYTES) {
      setFileError("Images must be 256 KB or smaller.");
      return;
    }
    const reader = new FileReader();
    reader.onload = () => {
      if (id === pickId.current) setImage(String(reader.result));
    };
    reader.onerror = () => {
      if (id === pickId.current) setFileError("Couldn't read that file.");
    };
    reader.readAsDataURL(file);
  };

  const save = () =>
    send(mode, mode === "emoji" ? emoji : mode === "image" ? (image ?? undefined) : undefined);

  return (
    <div className="space-y-2 text-sm">
      <div className="flex items-center gap-2 text-muted-foreground">
        Current icon <WorkstationIcon ws={ws} />
      </div>
      <div className="flex flex-wrap items-center gap-3">
        <span className="text-muted-foreground">Icon</span>
        <div role="group" aria-label="Icon type" className="flex overflow-hidden rounded-md border border-border text-xs">
          {MODES.map((m) => (
            <button
              key={m.key}
              type="button"
              aria-pressed={mode === m.key}
              onClick={() => setMode(m.key)}
              className={cn(
                "px-2 py-1 transition-colors",
                mode === m.key
                  ? "bg-primary text-primary-foreground"
                  : "bg-background text-muted-foreground hover:text-foreground"
              )}
            >
              {m.label}
            </button>
          ))}
        </div>
        {mode === "emoji" && (
          <input
            aria-label="Emoji"
            value={emoji}
            onChange={(e) => setEmoji(e.target.value)}
            maxLength={16}
            aria-invalid={emojiErr ? true : undefined}
            aria-describedby={emojiErr ? `icon-error-${ws.id}` : undefined}
            placeholder="🖥️"
            className="w-16 rounded border border-border bg-surface px-1 py-0.5 text-center"
          />
        )}
        {mode === "image" && (
          <>
            <label className="cursor-pointer rounded-md border border-border px-2 py-1 text-xs hover:bg-muted">
              Upload image
              <input
                key={fileKey}
                type="file"
                aria-label="Upload image"
                accept=".png,.svg,.ico,.webp"
                className="sr-only"
                onChange={(e) => pick(e.target.files?.[0])}
              />
            </label>
            {image && <img src={image} alt="" data-testid="icon-preview" className="h-6 w-6 rounded-md" />}
          </>
        )}
        {mode !== "auto" && (
          <Button size="sm" onClick={save} disabled={!canSave}>
            Save icon
          </Button>
        )}
        {ws.icon_kind !== "auto" && (
          <Button size="sm" variant="secondary" onClick={reset} disabled={saving}>
            Reset to auto
          </Button>
        )}
      </div>
      {(emojiErr || fileError) && <p id={`icon-error-${ws.id}`} role="alert" className="text-xs text-rose-400">{emojiErr ?? fileError}</p>}
    </div>
  );
}
