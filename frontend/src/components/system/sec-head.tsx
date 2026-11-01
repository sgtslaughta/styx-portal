import type { ReactNode } from "react";

/** Section heading with a gold rule (Glance .sec-head). */
export function SecHead({ title, hint, children }: { title: string; hint?: string; children?: ReactNode }) {
  return (
    <div className="mb-3 flex items-center gap-3">
      <h2 className="text-base font-semibold">{title}</h2>
      <span aria-hidden className="h-px flex-1 bg-[var(--obol-solid)] opacity-40" />
      {hint && <small className="text-xs text-muted-foreground">{hint}</small>}
      {children}
    </div>
  );
}
