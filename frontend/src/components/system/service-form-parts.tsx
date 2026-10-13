import type { ReactNode } from "react";
import { Plus, Trash2 } from "lucide-react";
import type { BypassRule } from "@/api/client";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { RISK, RiskCallout } from "@/components/common/risk-callout";
import { cn } from "@/lib/utils";
import { BYPASS_PREFIX_ERROR, type FieldErrors } from "./service-validation";

export const selectCls =
  "h-9 w-full rounded-md border border-input bg-transparent px-3 text-sm shadow-xs outline-none dark:bg-input/30 " +
  "focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50 disabled:cursor-not-allowed disabled:opacity-50 " +
  "aria-invalid:border-destructive";

export function Field({ id, label, error, hint, className, children }: {
  id: string; label: string; error?: string; hint?: ReactNode; className?: string; children: ReactNode;
}) {
  return (
    <div className={cn("space-y-1.5", className)}>
      <Label htmlFor={id}>{label}</Label>
      {children}
      {error ? <p id={`${id}-err`} className="text-xs text-destructive">{error}</p>
        : hint ? <p className="text-xs text-muted-foreground">{hint}</p> : null}
    </div>
  );
}

export function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <fieldset className="space-y-3 border-t border-border pt-4 first:border-0 first:pt-0">
      <legend className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">{title}</legend>
      {children}
    </fieldset>
  );
}

export function BypassRulesEditor({ rules, errors, onChange }: {
  rules: BypassRule[]; errors: FieldErrors; onChange: (r: BypassRule[]) => void;
}) {
  const setRule = (i: number, r: Partial<BypassRule>) => onChange(rules.map((x, j) => (j === i ? { ...x, ...r } : x)));
  return (
    <div className="space-y-3">
      {rules.length === 0 && (
        <p className="text-xs text-muted-foreground">
          No bypass rules. Add one only for paths that must work without a Styx login, such as an app API used by mobile clients.
        </p>
      )}
      {rules.map((r, i) => (
        <div key={i} className="space-y-2 rounded-md border border-border bg-surface p-3">
          <div className="flex items-start gap-2">
            <div className="grid flex-1 gap-2 sm:grid-cols-2">
              <div>
                <Input aria-label="Bypass path prefix" placeholder="/slug/api" value={r.path_prefix}
                  aria-invalid={!!errors[`bypass_${i}`]} autoFocus={r.path_prefix === "" && i === rules.length - 1}
                  onChange={(e) => setRule(i, { path_prefix: e.target.value })} />
                {errors[`bypass_${i}`] && (
                  <p className="mt-1 text-xs text-destructive">
                    {r.path_prefix && !r.path_prefix.startsWith("/") ? "Path prefix must start with /" : BYPASS_PREFIX_ERROR}
                  </p>
                )}
              </div>
              <div>
                <Input aria-label="Required header" placeholder="X-Api-Key (optional)" value={r.required_header ?? ""}
                  aria-invalid={!!errors[`bypass_header_${i}`]}
                  onChange={(e) => setRule(i, { required_header: e.target.value || null })} />
                {errors[`bypass_header_${i}`] && <p className="mt-1 text-xs text-destructive">{errors[`bypass_header_${i}`]}</p>}
              </div>
            </div>
            <Button type="button" variant="ghost" size="icon-sm" aria-label={`Remove bypass rule ${i + 1}`}
              onClick={() => onChange(rules.filter((_, j) => j !== i))}>
              <Trash2 className="h-4 w-4" />
            </Button>
          </div>
          <RiskCallout>{RISK.bypass(r.path_prefix || "<prefix>")}</RiskCallout>
        </div>
      ))}
      <Button type="button" variant="outline" size="sm"
        onClick={() => onChange([...rules, { path_prefix: "", required_header: null }])}>
        <Plus className="h-4 w-4" /> Add bypass rule
      </Button>
    </div>
  );
}
