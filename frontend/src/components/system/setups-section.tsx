import { useState } from "react";
import { Pencil, Plus, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { SectionHead } from "@/components/common/section-head";
import { ConfirmDialog } from "@/components/common/confirm-dialog";
import { TemplateBuilderModal } from "@/components/templates/template-builder-modal";
import { useTemplates, useDeleteTemplate } from "@/hooks/use-templates";
import { useAuth } from "@/hooks/use-auth";
import type { ServiceTemplate } from "@/lib/types";

const sizeOf = (t: ServiceTemplate) =>
  [t.cpu_limit && `${t.cpu_limit} CPU`, t.memory_limit].filter(Boolean).join(" · ") || "—";

type Editing = { mode: "new" | "edit"; template: ServiceTemplate | null } | null;

function Rows({ rows, onEdit, onDelete }: {
  rows: ServiceTemplate[]; onEdit: (t: ServiceTemplate) => void; onDelete: (t: ServiceTemplate) => void;
}) {
  return (
    <ul className="space-y-1.5">
      {rows.map((t) => (
        <li key={t.id} className="styx-card flex items-center gap-3 rounded-lg px-4 py-2.5">
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-medium">{t.display_name || t.name}</p>
            <p className="truncate font-mono text-[11px] text-muted-foreground">{t.image} · {sizeOf(t)}</p>
          </div>
          <button type="button" onClick={() => onEdit(t)} aria-label={`Edit ${t.display_name || t.name}`}
            className="rounded-md p-1.5 text-muted-foreground hover:bg-accent hover:text-foreground">
            <Pencil className="h-3.5 w-3.5" />
          </button>
          <button type="button" onClick={() => onDelete(t)} aria-label={`Delete ${t.display_name || t.name}`}
            className="rounded-md p-1.5 text-muted-foreground hover:bg-destructive/10 hover:text-destructive">
            <Trash2 className="h-3.5 w-3.5" />
          </button>
        </li>
      ))}
    </ul>
  );
}

/** Setups (shared templates) with New / Edit / Delete, plus the current user's private templates. */
export function SetupsSection({ only }: { only?: "mine" }) {
  const { user } = useAuth();
  const { data: shared = [] } = useTemplates({ shared: true });
  const showShared = only !== "mine";
  const { data: all = [] } = useTemplates();
  const del = useDeleteTemplate();
  const [editing, setEditing] = useState<Editing>(null);
  const [pending, setPending] = useState<ServiceTemplate | null>(null);
  const mine = all.filter((t) => !t.shared && t.owner_id && t.owner_id === user?.id);

  if (only === "mine" && mine.length === 0 && !editing) return null;
  return (
    <section aria-label="Setups" className="space-y-6">
      {showShared && <div>
        <SectionHead title="Setups" note="Shared launch presets" action={
          <button type="button" onClick={() => setEditing({ mode: "new", template: null })}
            className="ml-auto inline-flex items-center gap-1.5 rounded-md border border-border px-3 py-1.5 text-xs hover:bg-accent">
            <Plus className="h-3 w-3" />New setup
          </button>} />
        {shared.length === 0
          ? <p className="text-sm text-muted-foreground">No shared setups yet.</p>
          : <Rows rows={shared} onEdit={(t) => setEditing({ mode: "edit", template: t })} onDelete={setPending} />}
      </div>}
      {mine.length > 0 && (
        <div>
          <SectionHead title="My templates" note="Private to you" />
          <Rows rows={mine} onEdit={(t) => setEditing({ mode: "edit", template: t })} onDelete={setPending} />
        </div>
      )}
      {editing && (
        <TemplateBuilderModal open mode={editing.mode} template={editing.template}
          sharedOnly={editing.mode === "new"} onClose={() => setEditing(null)} />
      )}
      <ConfirmDialog open={!!pending} onOpenChange={(o) => !o && setPending(null)}
        title={`Delete ${pending ? pending.display_name || pending.name : ""}?`}
        description="Running instances keep working; new launches can no longer use it."
        variant="destructive" confirmLabel="Delete"
        onConfirm={() => {
          const t = pending; setPending(null);
          if (t) del.mutate(t.id, {
            onSuccess: () => toast.success("Deleted"),
            onError: (e) => toast.error(e.message),
          });
        }} />
    </section>
  );
}
