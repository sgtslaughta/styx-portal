import { useEffect, useState } from "react";
import { RotateCw } from "lucide-react";

interface ThumbnailProps {
  /** Image URL; a cache-busting `?t=` tick is appended on every refresh. */
  src: string;
  icon: string | null;
  isLive?: boolean;
  /** Fill the parent's height (for equal-height column layouts) instead of 16:9. */
  fill?: boolean;
  refreshMs?: number;
  /** When given, shows a refresh button that awaits this, then re-fetches the image. */
  onRefresh?: () => Promise<unknown>;
  /** Small tile (list rows/cards): smaller fallback icon. */
  small?: boolean;
  className?: string;
}

/**
 * Preview tile: shows `src` refreshed on an interval, falling back to the icon
 * when the image is unavailable (404/error) or `isLive` is false.
 */
export function Thumbnail({ src, icon, isLive = true, fill, refreshMs = 60000, onRefresh, small, className }: ThumbnailProps) {
  const [tick, setTick] = useState(0);
  const [shotOk, setShotOk] = useState(false);
  const [refreshing, setRefreshing] = useState(false);

  useEffect(() => {
    if (!isLive) {
      setShotOk(false);
      return;
    }
    const t = setInterval(() => setTick((n) => n + 1), refreshMs);
    return () => clearInterval(t);
  }, [isLive, refreshMs]);

  const handleRefresh = async () => {
    if (refreshing) return;
    setRefreshing(true);
    try {
      await onRefresh?.();
      setTick((n) => n + 1); // re-fetch the freshly captured frame
    } catch {
      // ignore — the existing image stays
    } finally {
      setRefreshing(false);
    }
  };

  const iconContent = icon?.startsWith("http") || icon?.startsWith("/") ? (
    <img src={icon} alt="" className={`${small ? "w-8 h-8" : "w-20 h-20"} object-contain opacity-60`} draggable={false} />
  ) : (
    <span className={`${small ? "text-3xl" : "text-7xl"} leading-none select-none opacity-60`}>{icon ?? "🖥️"}</span>
  );

  return (
    <div className={`relative w-full ${className ?? ""} rounded-lg border border-border bg-secondary overflow-hidden flex items-center justify-center ${fill ? "h-full min-h-[200px]" : "aspect-video"}`}>
      <div className={`flex items-center justify-center ${shotOk ? "hidden" : ""}`}>
        {iconContent}
      </div>
      {isLive && (
        <img
          src={`${src}?t=${tick}`}
          alt="Live preview"
          className={`absolute inset-0 w-full h-full object-cover transition-opacity duration-300 ${shotOk ? "opacity-100" : "opacity-0"}`}
          draggable={false}
          onLoad={() => setShotOk(true)}
          onError={() => setShotOk(false)}
        />
      )}
      {isLive && onRefresh && (
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
