import { statusMeta } from "@/lib/status";
import type { Instance } from "@/lib/types";

interface IconViewportProps {
  instance: Instance;
  icon: string | null;
}

export function IconViewport({ instance, icon }: IconViewportProps) {
  const { dotClass, pulse } = statusMeta(instance.status);

  const isStopped = instance.status === "stopped" || instance.status === "error";
  const isPaused = instance.status === "paused";

  const iconContent = instance.status === "pulling" ? (
    <span className="text-[16rem] leading-none select-none">⏳</span>
  ) : icon?.startsWith("http") ? (
    <img src={icon} alt={instance.name} className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[130%] h-[130%] object-contain" draggable={false} />
  ) : (
    <span className="text-[16rem] leading-none select-none">{icon ?? "🖥️"}</span>
  );

  return (
    <div className="relative aspect-video w-full bg-secondary overflow-hidden flex items-center justify-center">
      {/* Static icon — no infinite loops */}
      <div
        className={`relative flex items-center justify-center w-full h-full ${isStopped ? "grayscale opacity-20" : isPaused ? "opacity-40 saturate-50" : ""}`}
      >
        {iconContent}
      </div>

      {/* Name overlay gradient */}
      <div className="absolute bottom-0 left-0 right-0 px-3 pb-2 pt-8" style={{ background: "linear-gradient(to top, rgba(0,0,0,0.7) 0%, transparent 100%)" }}>
        <h3 className="text-lg font-bold text-white truncate drop-shadow-lg">{instance.name}</h3>
      </div>

      {/* Status dot */}
      <div
        className={`absolute top-2.5 right-2.5 h-3 w-3 rounded-full ${dotClass} ${pulse ? "animate-pulse" : ""}`}
      />
    </div>
  );
}
