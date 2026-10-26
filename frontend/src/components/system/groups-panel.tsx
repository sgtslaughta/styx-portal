import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { Plus, Trash2, UsersRound } from "lucide-react";
import { api, type Group, type ProxiedService } from "@/api/client";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
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
    <div className="space-y-6">
      <Card className="styx-card">
        <CardHeader>
          <div className="flex items-center gap-3">
            <div className="rounded-lg bg-primary/10 p-2">
              <UsersRound className="h-5 w-5 text-primary" />
            </div>
            <div>
              <CardTitle>Access groups</CardTitle>
              <CardDescription>Restrict a service to a group, then add users to that group from Users.</CardDescription>
            </div>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          <form
            className="flex flex-wrap items-end gap-3"
            onSubmit={(e) => { e.preventDefault(); if (name.trim()) void create(); }}
          >
            <div className="w-full space-y-1.5 sm:w-56">
              <Label htmlFor="group-name">Group name</Label>
              <Input id="group-name" value={name} maxLength={64} autoComplete="off"
                     placeholder="media" onChange={(e) => setName(e.target.value)} />
            </div>
            <div className="w-full flex-1 space-y-1.5 sm:w-auto sm:min-w-48">
              <Label htmlFor="group-desc">Description (optional)</Label>
              <Input id="group-desc" value={desc} maxLength={255} autoComplete="off"
                     onChange={(e) => setDesc(e.target.value)} />
            </div>
            <Button type="submit" aria-label="Add group" className="w-full sm:w-auto" disabled={!name.trim() || adding}>
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
            <div className="flex flex-col items-center gap-2 rounded-lg border border-dashed border-border px-4 py-8 text-center">
              <UsersRound className="h-8 w-8 text-muted-foreground/50" />
              <p className="text-sm font-medium">No groups yet</p>
              <p className="max-w-sm text-sm text-muted-foreground">
                Without groups, every logged-in user can open every service. Create one above to restrict access.
              </p>
            </div>
          ) : (
            <ul className="space-y-2">
              {groups.map((g) => (
                <li key={g.id} className="flex items-center justify-between gap-3 rounded-lg border border-border bg-muted/30 p-3">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="truncate font-medium">{g.name}</span>
                      <Badge variant="secondary">
                        {g.member_count} {g.member_count === 1 ? "member" : "members"}
                      </Badge>
                    </div>
                    {g.description && (
                      <p className="truncate text-xs text-muted-foreground" title={g.description}>{g.description}</p>
                    )}
                  </div>
                  <label className="flex shrink-0 items-center gap-2 text-xs text-muted-foreground">
                    <Switch checked={g.allow_gpu} aria-label={`Allow GPU for ${g.name}`}
                            onCheckedChange={(v) => void toggleGpu(g, v)} />
                    Allow GPU
                  </label>
                  <Button variant="ghost" size="icon-sm" title="Delete group"
                          className="shrink-0 text-muted-foreground hover:bg-destructive/10 hover:text-destructive"
                          aria-label={`Delete ${g.name}`} onClick={() => setTarget(g)}>
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

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
    </div>
  );
}
