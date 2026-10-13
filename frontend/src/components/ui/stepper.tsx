import { Check, Circle, Loader2, Minus, X } from "lucide-react";
import { cn } from "@/lib/utils";

export type StepItem = { id: string; label: string;
  state: "pending" | "active" | "done" | "failed" | "skipped"; detail?: string | null; percent?: number | null; title?: string };

const ICON = {
  pending: <Circle className="h-4 w-4 text-muted-foreground" />,
  active: <Loader2 className="h-4 w-4 animate-spin text-primary motion-reduce:animate-none" />,
  done: <Check className="h-4 w-4 text-success-foreground" />,
  failed: <X className="h-4 w-4 text-destructive" />,
  skipped: <Minus className="h-4 w-4 text-muted-foreground" />,
};
const SR = { pending: "Not started", active: "In progress", done: "Done", failed: "Failed", skipped: "Skipped" };

/** Numbered sequence (the content is a real sequence: backup, apply, restart, verify, or pull, start). */
export function Stepper({ steps, className }: { steps: StepItem[]; className?: string }) {
  return (
    <ol className={cn("space-y-3", className)}>
      {steps.map((s, i) => (
        <li key={s.id} aria-current={s.state === "active" ? "step" : undefined} className="flex gap-3">
          <span className={cn("flex h-7 w-7 shrink-0 items-center justify-center rounded-full border",
            s.state === "done" ? "border-success/50" : s.state === "failed" ? "border-destructive/60"
              : s.state === "active" ? "border-primary" : "border-input")}>
            {s.state === "pending" ? <span className="text-xs text-muted-foreground">{i + 1}</span> : ICON[s.state]}
          </span>
          <div className="min-w-0 flex-1 pt-0.5">
            <p className={cn("text-sm", s.state === "pending" || s.state === "skipped" ? "text-muted-foreground" : "font-medium")}>
              {s.label}<span className="sr-only"> ({SR[s.state]})</span>
              {s.percent != null && s.state === "active" && (
                <span className="ml-2 text-xs font-normal tabular-nums text-muted-foreground" aria-hidden>{Math.round(s.percent)}%</span>
              )}
            </p>
            {s.percent != null && s.state === "active" && (
              <div role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(s.percent)} aria-valuetext={`${Math.round(s.percent)}%`}
                aria-label={s.label} className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-muted">
                <div className="h-full bg-primary transition-[width] motion-reduce:transition-none" style={{ width: `${s.percent}%` }} />
              </div>
            )}
            {s.detail && <p title={s.title} className={cn("mt-1 text-xs", s.title ? "truncate" : "break-words", s.state === "failed" ? "text-destructive" : "text-muted-foreground")}>{s.detail}</p>}
          </div>
        </li>
      ))}
    </ol>
  );
}
