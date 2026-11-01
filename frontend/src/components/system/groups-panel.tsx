import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import "@/styles/admin-table.css";
import { Plus, Trash2 } from "lucide-react";
import { api, type Group, type ProxiedService } from "@/api/client";
import { SectionHead } from "@/components/common/section-head";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";
import { ConfirmDialog } from "@/components/common/confirm-dialog";

const errMsg = (e: unknown, fallback: string) => (e instanceof Error && e.message ? e.message : fallback);

export function GroupsPanel() {
  const [groups, setGroups] = useState<Group[] | null>(null);
  const [services, setServices] = useState<ProxiedService[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [desc, setDesc] = useState("");
  const [adding, setAdding] = useState(false);
  const [target, setTarget] = useState<Group | null>(null);

  const load = useCallback(async () => {
    try {
      const [g, s] = await Promise.all([api.listGroups(), api.listServices()]);
      setGroups(g);
      setServices(s);
      setError(null);
    } catch (e) {
      setError(errMsg(e, "Failed to load groups"));
    }
  }, []);
  useEffect(() => { void load(); }, [load]);

  const create = async () => {
    setAdding(true);
    try {
      await api.createGroup({ name: name.trim(), description: desc.trim() || null });
      setName("");
      setDesc("");
      toast.success("Group created");
      await load();
    } catch (e) {
      toast.error(errMsg(e, "Failed to create group"));
    } finally {
      setAdding(false);
    }
  };

  const toggleGpu = async (g: Group, allow: boolean) => {
    try {
      await api.updateGroup(g.id, { allow_gpu: allow });
      await load();
    } catch (e) {
      toast.error(errMsg(e, "Failed to update group"));
    }
  };

  const remove = async () => {
    if (!target) return;
    try {
      await api.deleteGroup(target.id);
      toast.success("Group deleted");
      await load();
    } catch (e) {
      toast.error(errMsg(e, "Failed to delete group"));
    }
  };

  const affected = target ? services.filter((s) => s.allowed_groups.includes(target.name)) : [];

  return (
    <section>
      <SectionHead title="Groups" note="Restrict a service to a group, then add users to it from Users." />
      <form className="toolbar" onSubmit={(e) => { e.preventDefault(); if (name.trim()) void create(); }}>
        <Label htmlFor="group-name" className="sr-only">Group name</Label>
        <Input id="group-name" value={name} maxLength={64} autoComplete="off" placeholder="New group name"
               className="max-w-56" onChange={(e) => setName(e.target.value)} />
        <Label htmlFor="group-desc" className="sr-only">Description (optional)</Label>
        <Input id="group-desc" value={desc} maxLength={255} autoComplete="off" placeholder="Description (optional)"
               className="max-w-72" onChange={(e) => setDesc(e.target.value)} />
        <Button type="submit" aria-label="Add group" variant="secondary" disabled={!name.trim() || adding}>
          <Plus className="h-4 w-4" /> {adding ? "Adding..." : "Add group"}
        </Button>
      </form>

      {error ? (
        <div role="alert" className="flex items-center justify-between rounded-md border border-destructive/20 bg-destructive/5 p-3">
          <p className="text-sm text-destructive">{error}</p>
          <Button size="sm" variant="secondary" onClick={() => void load()}>Retry</Button>
        </div>
      ) : groups === null ? (
        <p className="text-sm text-muted-foreground">Loading groups...</p>
      ) : groups.length === 0 ? (
        <div className="rounded-lg border border-dashed border-border px-4 py-8 text-center">
          <p className="text-sm font-medium">No groups yet</p>
          <p className="mx-auto max-w-sm text-sm text-muted-foreground">
            Without groups, every logged-in user can open every service. Create one above to restrict access.
          </p>
        </div>
      ) : (
        <table className="dense">
          <thead><tr><th>Name</th><th>Members</th><th>Allow GPU</th><th /></tr></thead>
          <tbody>
            {groups.map((g) => (
              <tr key={g.id}>
                <td><strong>{g.name}</strong>{g.description && <small title={g.description}>{g.description}</small>}</td>
                <td>{g.member_count} {g.member_count === 1 ? "member" : "members"}</td>
                <td>
                  <Switch checked={g.allow_gpu} aria-label={`Allow GPU for ${g.name}`}
                          onCheckedChange={(v) => void toggleGpu(g, v)} />
                </td>
                <td className="acts">
                  <Button variant="ghost" size="icon-sm" title="Delete group" aria-label={`Delete ${g.name}`}
                          className="hover:bg-destructive/10 hover:text-destructive" onClick={() => setTarget(g)}>
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <ConfirmDialog
        open={target !== null}
        onOpenChange={(o) => { if (!o) setTarget(null); }}
        title={`Delete group ${target?.name ?? ""}?`}
        variant="destructive"
        confirmLabel="Delete"
        description={affected.length ? (
          <>
            These services require this group: <strong>{affected.map((s) => s.name).join(", ")}</strong>.
            After deletion only admins will be able to open them until you edit their allowed groups.
          </>
        ) : "Members lose this group immediately."}
        onConfirm={() => void remove()}
      />
    </section>
  );
}
