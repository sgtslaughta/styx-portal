import { useEffect, useState } from "react";
import { RotateCw } from "lucide-react";
import { api } from "@/api/client";

interface InstanceThumbnailProps {
  instanceId: string;
  icon: string | null;
  isLive: boolean;
  /** Fill the parent's height (for equal-height column layouts) instead of 16:9. */
  fill?: boolean;
}

const REFRESH_MS = 30000;

/**
 * Live preview tile for the detail pane: shows the cached screenshot for a
 * running/idle instance, refreshed every 30s, falling back to the template
 * icon when no screenshot is available (404/error) or the instance isn't live.
 * Unlike IconViewport it carries no name/status overlay — the pane header owns those.
 */
export function InstanceThumbnail({ instanceId, icon, isLive, fill }: InstanceThumbnailProps) {
  const [tick, setTick] = useState(0);
  const [shotOk, setShotOk] = useState(false);
  const [refreshing, setRefreshing] = useState(false);

  useEffect(() => {
    if (!isLive) {
      setShotOk(false);
      return;
    }
    const t = setInterval(() => setTick((n) => n + 1), REFRESH_MS);
    return () => clearInterval(t);
  }, [isLive]);

  const handleRefresh = async () => {
    if (refreshing) return;
    setRefreshing(true);
    try {
      await api.refreshScreenshot(instanceId);
      setTick((n) => n + 1); // re-fetch the freshly captured frame
    } catch {
      // ignore — the existing image stays
    } finally {
      setRefreshing(false);
    }
  };

  const iconContent = icon?.startsWith("http") ? (
    <img src={icon} alt="" className="w-20 h-20 object-contain opacity-60" draggable={false} />
  ) : (
    <span className="text-7xl leading-none select-none opacity-60">{icon ?? "🖥️"}</span>
  );

  return (
    <div className={`relative w-full rounded-lg border border-border bg-secondary overflow-hidden flex items-center justify-center ${fill ? "h-full min-h-[200px]" : "aspect-video"}`}>
      <div className={`flex items-center justify-center ${shotOk ? "hidden" : ""}`}>
        {iconContent}
      </div>
      {isLive && (
        <img
          src={`${api.screenshotUrl(instanceId)}?t=${tick}`}
          alt="Live preview"
          className={`absolute inset-0 w-full h-full object-cover transition-opacity duration-300 ${shotOk ? "opacity-100" : "opacity-0"}`}
          draggable={false}
          onLoad={() => setShotOk(true)}
          onError={() => setShotOk(false)}
        />
      )}
      {isLive && (
        <button
          type="button"
          onClick={handleRefresh}
          disabled={refreshing}
          title="Refresh preview"
          aria-label="Refresh preview"
          className="absolute top-2 right-2 rounded-md bg-black/50 p-1.5 text-white/90 backdrop-blur-sm transition hover:bg-black/70 disabled:opacity-50"
        >
          <RotateCw className={`h-4 w-4 ${refreshing ? "animate-spin" : ""}`} />
        </button>
      )}
    </div>
  );
}
