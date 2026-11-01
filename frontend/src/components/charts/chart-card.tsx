import type { ReactNode } from "react";
import { slotVar, type Slot } from "./axis";

export function Legend({ items }: { items: { name: string; slot: Slot }[] }) {
  if (items.length < 2) return null;
  return (
    <div className="mb-0.5 flex flex-wrap gap-x-3 gap-y-1 text-xs text-muted-foreground">
      {items.map((s) => (
        <span key={s.name} className="whitespace-nowrap">
          <i className="mr-1.5 inline-block h-[3px] w-2.5 rounded-sm align-middle" style={{ background: slotVar(s.slot) }} />
          {s.name}
        </span>
      ))}
    </div>
  );
}

/** Equal-height chart panel: header, optional legend, then a flex-1 body. */
export function ChartCard({ title, hint, action, legend, children }: {
  title: string; hint?: string; action?: ReactNode; legend?: { name: string; slot: Slot }[]; children: ReactNode;
}) {
  return (
    <section className="flex min-w-0 flex-col rounded-xl border border-border bg-card/55 px-4 pb-2.5 pt-3.5" aria-label={title}>
      <div className="mb-1.5 flex items-center gap-2">
        <h3 className="flex-1 text-sm font-semibold">{title}</h3>
        {hint && <small className="text-xs text-muted-foreground">{hint}</small>}
        {action}
      </div>
      {legend && <Legend items={legend} />}
      <div className="flex min-h-[170px] flex-1 flex-col">{children}</div>
    </section>
  );
}
