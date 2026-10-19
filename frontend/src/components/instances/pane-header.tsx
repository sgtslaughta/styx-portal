import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

/** Hero (large icon on a tinted panel, status dot + label) and title row, shared by both workspace kinds. */
export function PaneHeader({ icon, title, status, dotClass, actions, muted }: {
  icon: ReactNode; title: string; status: string; dotClass: string; actions?: ReactNode; muted?: boolean;
}) {
  return (
    <div className="shrink-0 border-b border-border">
      <div data-testid="pane-hero"
        className={cn("flex flex-col items-center gap-2 bg-primary/10 px-4 py-4", muted && "opacity-60 grayscale")}>
        {icon}
        <span aria-hidden className="flex items-center gap-1.5 text-xs font-medium">
          <span className={cn("size-2 rounded-full", dotClass)} />{status}
        </span>
      </div>
      <div className="flex flex-wrap items-center gap-3 p-4">
        <div className="min-w-0 flex-1">
          <h2 className="truncate text-lg font-semibold" title={title}>{title}</h2>
          <p className="text-xs text-muted-foreground">{status}</p>
        </div>
        {actions}
      </div>
    </div>
  );
}
