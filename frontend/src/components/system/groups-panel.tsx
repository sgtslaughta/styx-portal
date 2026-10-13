import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { Trash2, UsersRound } from "lucide-react";
import { api, type Group, type ProxiedService } from "@/api/client";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
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
        <CardHeader className="pb-4">
          <div className="flex items-center gap-3">
            <div className="rounded-lg bg-primary/10 p-2">
              <UsersRound className="h-5 w-5 text-primary" />
            </div>
            <div>
              <CardTitle>Groups</CardTitle>
              <CardDescription>Groups decide which users may open a proxied service</CardDescription>
            </div>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          <form
            className="flex flex-wrap items-end gap-3"
            onSubmit={(e) => { e.preventDefault(); if (name.trim()) void create(); }}
          >
            <div className="space-y-1.5">
              <Label htmlFor="group-name">Group name</Label>
              <Input id="group-name" value={name} maxLength={64} autoComplete="off"
                     placeholder="media" onChange={(e) => setName(e.target.value)} />
            </div>
            <div className="min-w-48 flex-1 space-y-1.5">
              <Label htmlFor="group-desc">Description (optional)</Label>
              <Input id="group-desc" value={desc} maxLength={255} autoComplete="off"
                     onChange={(e) => setDesc(e.target.value)} />
            </div>
            <Button type="submit" size="sm" aria-label="Add group" disabled={!name.trim() || adding}>
              {adding ? "Adding..." : "Add"}
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
            <div className="flex flex-col items-center gap-2 rounded-lg border border-border px-4 py-8">
              <UsersRound className="h-8 w-8 text-muted-foreground/40" />
              <span className="text-sm text-muted-foreground">No groups yet</span>
            </div>
          ) : (
            <ul className="space-y-2">
              {groups.map((g) => (
                <li key={g.id} className="flex items-center justify-between rounded-lg border border-border bg-surface p-3">
                  <div className="min-w-0">
                    <span className="font-medium">{g.name}</span>
                    <span className="ml-2 rounded bg-muted px-2 py-0.5 text-xs text-muted-foreground">
                      {g.member_count} {g.member_count === 1 ? "member" : "members"}
                    </span>
                    {g.description && (
                      <p className="truncate text-xs text-muted-foreground">{g.description}</p>
                    )}
                  </div>
                  <Button variant="destructive" size="sm" title="Delete group"
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
