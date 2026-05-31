import { cn } from "@/lib/utils";
import { statusMeta } from "@/lib/status";

export function StatusBadge({ status, showIcon = false }: { status: string; showIcon?: boolean }) {
  const m = statusMeta(status);
  const Icon = m.icon;
  return (
    <span className={cn("flex items-center gap-1.5 text-xs font-medium", m.textClass)}>
      {showIcon ? (
        <Icon className={cn("size-3", m.pulse && "animate-pulse")} />
      ) : (
        <span className={cn("h-1.5 w-1.5 rounded-full", m.dotClass, m.pulse && "animate-pulse")} />
      )}
      {m.label}
    </span>
  );
}
