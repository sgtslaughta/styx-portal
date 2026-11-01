import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useContext, useState } from "react";
import { AuthContext } from "@/auth/AuthContext";
import { toast } from "sonner";
import "@/styles/admin-table.css";
import { api } from "@/api/client";
import { SectionHead } from "@/components/common/section-head";
import { UserProfilesDialog } from "@/components/system/user-profiles-dialog";
import { UserGroupsDialog } from "@/components/system/user-groups-dialog";
import { ResetMatrixDialog } from "@/components/system/reset-matrix-dialog";
import { DeleteUserDialog, TempPasswordDialog } from "@/components/system/user-dialogs";
import { UsersBulkBar } from "@/components/system/users-bulk-bar";
import { UsersTable } from "@/components/system/users-table";
import { filterUsers, isUserLocked, type UserFilter } from "@/components/system/users-filters";
import type { UserActions } from "@/components/system/user-row-actions";

type Target = { id: string; username: string } | null;

function useAction<T>(fn: (id: string) => Promise<T>, msg?: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => fn(id),
    onError: (e: Error) => toast.error(e.message),
    onSuccess: () => { void qc.invalidateQueries({ queryKey: ["users"] }); if (msg) toast.success(msg); },
  });
}

export function UsersPanel() {
  const qc = useQueryClient();
  const { data: users = [] } = useQuery({ queryKey: ["users"], queryFn: api.listUsers });
  const selfId = useContext(AuthContext)?.user?.id;
  const { data: invites = [] } = useQuery({ queryKey: ["invites"], queryFn: api.listInvites });
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [filter, setFilter] = useState<UserFilter>("all");
  const [query, setQuery] = useState("");
  const [newLink, setNewLink] = useState<string | null>(null);
  const [tempPw, setTempPw] = useState<string | null>(null);
  const [deleteId, setDeleteId] = useState<string | null>(null);
  const [groupsFor, setGroupsFor] = useState<Target>(null);
  const [profilesFor, setProfilesFor] = useState<Target>(null);
  const [matrixFor, setMatrixFor] = useState<Target>(null);

  const refresh = () => qc.invalidateQueries({ queryKey: ["users"] });
  const onError = (e: Error) => toast.error(e.message);

  const invite = useMutation({
    mutationFn: () => api.createInvite({ role: "user" }),
    onSuccess: (r) => {
      const url = `${location.origin}/accept-invite/${r.token}`;
      void navigator.clipboard.writeText(url);
      setNewLink(url);
      toast.success("Invite link copied");
      void qc.invalidateQueries({ queryKey: ["invites"] });
      setFilter("invites");
    },
    onError,
  });
  const disable = useAction(api.disableUser);
  const unlock = useAction(api.unlockUser, "User unlocked");
  const forceChange = useAction(api.forcePasswordChange, "User forced to change password");
  const setRole = useMutation({
    mutationFn: (p: { id: string; role: string }) => api.changeRole(p.id, p.role), onError, onSuccess: () => void refresh(),
  });
  const reset = useMutation({
    mutationFn: (id: string) => api.resetUserPassword(id), onError,
    onSuccess: (d) => { setTempPw(d.temp_password); void refresh(); },
  });
  const del = useMutation({
    mutationFn: (id: string) => api.deleteUser(id), onError,
    onSuccess: () => { void refresh(); toast.success("User deleted"); setDeleteId(null); },
  });

  const actions: UserActions = {
    unlock: (u) => unlock.mutate(u.id), resetPassword: (u) => reset.mutate(u.id),
    forceChange: (u) => forceChange.mutate(u.id), disable: (u) => disable.mutate(u.id),
    askDelete: (u) => setDeleteId(u.id), groups: (u) => setGroupsFor(u),
    profiles: (u) => setProfilesFor(u), matrix: (u) => setMatrixFor(u),
  };
  const toggle = (id: string) => setSelected((s) => { const n = new Set(s); if (n.has(id)) n.delete(id); else n.add(id); return n; });
  const toggleAll = (ids: string[]) => setSelected((s) => ids.every((i) => s.has(i)) ? new Set() : new Set(ids));
  const bulk = async (ids: string[], fn: (id: string) => Promise<unknown>, done: string) => {
    const res = await Promise.allSettled(ids.map((i) => fn(i)));
    const failed = res.filter((r) => r.status === "rejected").length;
    if (failed) toast.error(`${failed} of ${ids.length} failed`); else toast.success(done);
    setSelected(new Set());
    void qc.invalidateQueries({ queryKey: ["users"] });
  };
  const ids = [...selected];

  const segs: [UserFilter, string, number][] = [
    ["all", "All", users.length],
    ["admins", "Admins", users.filter((u) => u.role === "admin").length],
    ["locked", "Locked", users.filter((u) => isUserLocked(u.locked_until)).length],
    ["invites", "Invites", invites.length],
  ];

  return (
    <section>
      <SectionHead title="Users" action={
        <button type="button" className="btn-gold" onClick={() => invite.mutate()} disabled={invite.isPending}>
          {invite.isPending ? "Generating…" : "Invite someone"}
        </button>
      } />
      <div className="toolbar">
        <input placeholder="Filter by name or email" aria-label="Filter users" value={query}
               onChange={(e) => setQuery(e.target.value)} />
        <div className="seg-s">
          {segs.map(([id, label, n]) => (
            <button key={id} type="button" aria-pressed={filter === id} onClick={() => setFilter(id)}>{label} {n}</button>
          ))}
        </div>
      </div>
      {newLink && filter === "invites" && (
        <p className="mb-2 text-xs text-muted-foreground">
          Link copied (single use, 72 hours): <code className="break-all">{newLink}</code>
        </p>
      )}
      <UsersBulkBar count={ids.length} onClear={() => setSelected(new Set())}
        onUnlock={() => void bulk(ids, api.unlockUser, "Users unlocked")}
        onDelete={() => void bulk(ids.filter((i) => i !== selfId), api.deleteUser, "Users deleted")} />
      <UsersTable users={filterUsers(users, filter, query)} invites={invites} showInvites={filter === "invites"}
                  actions={actions} selfId={selfId} selected={selected} toggle={toggle} toggleAll={toggleAll}
                  setRole={(id, role) => setRole.mutate({ id, role })} />

      <UserGroupsDialog open={groupsFor !== null} userId={groupsFor?.id ?? ""} username={groupsFor?.username ?? ""}
                        onOpenChange={(o) => { if (!o) setGroupsFor(null); }} />
      <UserProfilesDialog open={profilesFor !== null} userId={profilesFor?.id ?? ""} username={profilesFor?.username ?? ""}
                          onOpenChange={(o) => { if (!o) setProfilesFor(null); }} />
      <ResetMatrixDialog user={matrixFor} onClose={() => setMatrixFor(null)} />
      <TempPasswordDialog password={tempPw} onClose={() => setTempPw(null)} />
      <DeleteUserDialog username={users.find((u) => u.id === deleteId)?.username ?? null} pending={del.isPending}
                        onCancel={() => setDeleteId(null)} onConfirm={() => deleteId && del.mutate(deleteId)} />
    </section>
  );
}
