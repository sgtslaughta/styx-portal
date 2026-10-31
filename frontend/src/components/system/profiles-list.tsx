import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { Trash2 } from "lucide-react";
import { type Profile } from "@/api/client";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/common/confirm-dialog";

interface Props {
  load: () => Promise<Profile[]>;
  remove: (templateId: string) => Promise<unknown>;
  actionLabel: string;
}

export function ProfilesList({ load, remove, actionLabel }: Props) {
  const [items, setItems] = useState<Profile[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [target, setTarget] = useState<Profile | null>(null);

  const refresh = useCallback(() => {
    load().then((p) => { setItems(p); setError(null); })
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load profiles"));
  }, [load]);
  useEffect(() => { refresh(); }, [refresh]);

  const doRemove = async () => {
    if (!target) return;
    try {
      await remove(target.template_id);
      toast.success(`${actionLabel}: ${target.display_name}`);
      refresh();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Failed");
    }
  };

  if (error) return <p role="alert" className="text-sm text-destructive">{error}</p>;
  if (items === null) return <p className="text-sm text-muted-foreground">Loading profiles...</p>;
  if (items.length === 0) return <p className="text-sm text-muted-foreground">No profiles yet.</p>;
  return (
    <>
      <ul className="space-y-1.5">
        {items.map((p) => (
          <li key={p.template_id} className="flex items-center justify-between gap-3 rounded-md border border-border px-3 py-2 text-sm">
            <span className="min-w-0">
              <span className="block truncate font-medium">{p.display_name}</span>
              {p.in_use && <span className="block text-xs text-muted-foreground">In use by an instance</span>}
            </span>
            <Button size="sm" variant="ghost" disabled={p.in_use} onClick={() => setTarget(p)}
                    className="shrink-0 text-muted-foreground hover:text-destructive">
              <Trash2 className="h-4 w-4" /> {actionLabel}
            </Button>
          </li>
        ))}
      </ul>
      <ConfirmDialog
        open={target !== null}
        onOpenChange={(o) => { if (!o) setTarget(null); }}
        title={`${actionLabel} profile "${target?.display_name ?? ""}"?`}
        description="The saved profile data is permanently deleted."
        variant="destructive"
        confirmLabel={actionLabel}
        onConfirm={() => void doRemove()}
      />
    </>
  );
}
