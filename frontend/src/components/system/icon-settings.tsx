import { useEffect, useRef, useState, type ReactNode } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export type IconKind = "auto" | "emoji" | "image";
type Kind = IconKind;
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

type Props = {
  /** Current icon image URL (carries the etag, so it changes when the icon does). */
  iconUrl: string;
  kind: IconKind;
  /** Distinguishes the error element ids when several editors are on one page. */
  id: string;
  /** Persist the icon; reject with an Error to have its message shown. */
  onSave?: (kind: IconKind, value?: string) => Promise<unknown>;
  /** Staged mode (no Save/Reset buttons): report the pending change, or null for "no change". */
  onStage?: (change: { kind: IconKind; value?: string } | null) => void;
  /** Extra buttons, e.g. "Use the app's own icon". */
  extra?: ReactNode;
};

export function IconSettings({ iconUrl, kind, id, onSave, onStage, extra }: Props) {
  const [mode, setMode] = useState<Kind>(kind);
  const [emoji, setEmoji] = useState("");
  const [image, setImage] = useState<string | null>(null);
  const [fileError, setFileError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const pickId = useRef(0);
  const [fileKey, setFileKey] = useState(0);

  useEffect(() => {
    setMode(kind);
  }, [kind, iconUrl]);

  const stageRef = useRef(onStage);
  stageRef.current = onStage;
  useEffect(() => {
    const stage = stageRef.current;
    if (!stage) return;
    if (mode === "auto") stage(kind === "auto" ? null : { kind: "auto" });
    else if (mode === "emoji") stage(emojiError(emoji) === null ? { kind: "emoji", value: emoji } : null);
    else stage(image ? { kind: "image", value: image } : null);
  }, [mode, emoji, image, kind]);

  const emojiErr = mode === "emoji" && emoji ? emojiError(emoji) : null;
  const canSave = !saving && (mode === "emoji" ? emojiError(emoji) === null : image !== null);

  const send = async (k: Kind, value?: string): Promise<boolean> => {
    setSaving(true);
    try {
      await onSave?.(k, value);
      setEmoji("");
      setImage(null);
      setFileError(null);
      setFileKey((n) => n + 1);
      return true;
    } catch (e) {
      toast.error((e as Error).message);
      return false;
    } finally {
      setSaving(false);
    }
  };

  const reset = async () => {
    if (await send("auto")) setMode("auto");
    else setMode(kind);
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
        Current icon <img src={iconUrl} alt="" className="h-6 w-6 shrink-0 rounded-md" />
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
            aria-describedby={emojiErr ? `icon-error-${id}` : undefined}
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
        {mode !== "auto" && !onStage && (
          <Button size="sm" onClick={save} disabled={!canSave}>
            Save icon
          </Button>
        )}
        {kind !== "auto" && !onStage && (
          <Button size="sm" variant="secondary" onClick={reset} disabled={saving}>
            Reset to auto
          </Button>
        )}
        {extra}
      </div>
      {(emojiErr || fileError) && <p id={`icon-error-${id}`} role="alert" className="text-xs text-rose-400">{emojiErr ?? fileError}</p>}
    </div>
  );
}
