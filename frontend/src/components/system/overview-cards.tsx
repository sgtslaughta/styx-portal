import type { ReactNode } from "react";
import { CATEGORIES } from "@/components/settings/nav-config";
import { cn } from "@/lib/utils";

export type Level = "ok" | "warn" | "error";
const LEVEL = {
  ok: { text: "OK", cls: "border-success/40 bg-success/10 text-success" },
  warn: { text: "Warning", cls: "border-warning/40 bg-warning/10 text-warning-foreground" },
  error: { text: "Error", cls: "border-destructive/40 bg-destructive/10 text-destructive" },
} as const;

/** Navigates the settings layout; same section ids as nav-config. */
export const SECTION_EVENT = "styx:settings-section";

function sectionMeta(id: string) {
  for (const c of CATEGORIES) {
    const s = c.sections.find((x) => x.id === id);
    if (s) return s;
  }
  throw new Error(`unknown section ${id}`);
}

export function OverviewCard({ section, level, children }: { section: string; level: Level; children: ReactNode }) {
  const meta = sectionMeta(section);
  const Icon = meta.icon;
  const lv = LEVEL[level];
  return (
    <div className="styx-card flex flex-col gap-3 rounded-lg p-4" data-testid={`card-${section}`}>
      <div className="flex items-center justify-between gap-2">
        <span className="flex items-center gap-2 text-sm font-medium"><Icon className="h-4 w-4" />{meta.label}</span>
        <span className={cn("rounded-full border px-2 py-0.5 text-[11px] font-medium", lv.cls)}>{lv.text}</span>
      </div>
      <div className="flex-1 space-y-1 text-xs text-muted-foreground">{children}</div>
      <a
        href={`?section=${section}`}
        onClick={(e) => {
          e.preventDefault();
          window.dispatchEvent(new CustomEvent(SECTION_EVENT, { detail: section }));
        }}
        className="text-xs font-medium text-primary hover:underline"
      >
        View {meta.label.toLowerCase()} →
      </a>
    </div>
  );
}

export function Figure({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-2">
      <span>{label}</span>
      <span className="font-mono text-foreground tabular-nums">{value}</span>
    </div>
  );
}

export function Sparkline({ data, label }: { data: number[]; label: string }) {
  if (data.length < 2) return null;
  const max = Math.max(100, ...data);
  const pts = data.map((v, i) => `${((i / (data.length - 1)) * 100).toFixed(1)},${(24 - (v / max) * 22 - 1).toFixed(1)}`).join(" ");
  return (
    <svg viewBox="0 0 100 24" preserveAspectRatio="none" className="h-6 w-full" role="img" aria-label={label}>
      <polyline fill="none" stroke="currentColor" strokeWidth={1.5} className="text-primary" points={pts} />
    </svg>
  );
}
