import { useEffect, useState } from "react";
import { toast } from "sonner";
import { api, type Group } from "@/api/client";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";

interface Props {
  userId: string;
  username: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function UserGroupsDialog({ userId, username, open, onOpenChange }: Props) {
  const [groups, setGroups] = useState<Group[] | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!open || !userId) return;
    let live = true;
    setGroups(null);
    setError(null);
    Promise.all([api.listGroups(), api.getUserGroups(userId)])
      .then(([g, mine]) => { if (live) { setGroups(g); setSelected(new Set(mine)); } })
      .catch((e) => { if (live) setError(e instanceof Error ? e.message : "Failed to load groups"); });
    return () => { live = false; };
  }, [open, userId]);

  const toggle = (id: string, on: boolean) =>
    setSelected((prev) => {
      const next = new Set(prev);
      if (on) next.add(id); else next.delete(id);
      return next;
    });

  const save = async () => {
    setSaving(true);
    try {
      await api.setUserGroups(userId, [...selected]);
      toast.success(`Groups updated for ${username}`);
      onOpenChange(false);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Failed to save groups");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Groups for {username}</DialogTitle>
          <DialogDescription>
            Services restricted to a group are only visible to its members. Admins always see every service.
          </DialogDescription>
        </DialogHeader>
        {error ? (
          <p role="alert" className="text-sm text-destructive">{error}</p>
        ) : groups === null ? (
          <p className="text-sm text-muted-foreground">Loading groups...</p>
        ) : groups.length === 0 ? (
          <p className="text-sm text-muted-foreground">No groups defined yet. Create one in Administration, Groups.</p>
        ) : (
          <fieldset className="max-h-72 space-y-2 overflow-y-auto text-sm">
            <legend className="sr-only">Groups</legend>
            {groups.map((g) => (
              <label key={g.id} className="flex items-center gap-2">
                <input type="checkbox" checked={selected.has(g.id)}
                       onChange={(e) => toggle(g.id, e.target.checked)} />
                {g.name}
              </label>
            ))}
          </fieldset>
        )}
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button onClick={() => void save()} disabled={groups === null || saving}>
            {saving ? "Saving..." : "Save"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
