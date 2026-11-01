import { Copy } from "lucide-react";
import { Button } from "@/components/ui/button";
import { UserGroupChips } from "@/components/system/user-group-chips";
import { UserRowActions, type UserActions } from "@/components/system/user-row-actions";
import { formatRelativeTime, isUserLocked, type UserRow } from "@/components/system/users-filters";

type Props = {
  users: UserRow[];
  invites: string[];
  showInvites: boolean;
  actions: UserActions;
  setRole: (id: string, role: string) => void;
  copyInvite: (url: string) => void;
};

export function UsersTable({ users, invites, showInvites, actions, setRole, copyInvite }: Props) {
  const empty = showInvites ? invites.length === 0 : users.length === 0;
  return (
    <table className="dense full">
      <thead>
        <tr><th>Name</th><th>Role</th><th>Groups</th><th>Sign-in card</th><th>Last sign-in</th><th /></tr>
      </thead>
      <tbody>
        {showInvites && invites.map((url) => (
          <tr key={url}>
            <td><strong>Invite link</strong><small>Single use, valid 72 hours</small></td>
            <td className="text-muted-foreground">User</td><td className="text-muted-foreground">None</td>
            <td className="text-muted-foreground">Not set</td><td className="text-muted-foreground">Invite pending</td>
            <td className="acts">
              <Button variant="ghost" size="sm" onClick={() => copyInvite(url)}><Copy className="h-3.5 w-3.5" />Copy link</Button>
            </td>
          </tr>
        ))}
        {!showInvites && users.map((u) => {
          const locked = isUserLocked(u.locked_until);
          return (
            <tr key={u.id} className={locked ? "warn" : undefined}>
              <td>
                <strong>{u.username}</strong>
                <small>{u.email || (u.is_active ? "" : "Disabled")}</small>
              </td>
              <td>
                <select aria-label={`Role for ${u.username}`} value={u.role} disabled={!u.is_active}
                        onChange={(e) => setRole(u.id, e.target.value)}>
                  <option value="admin">Admin</option><option value="user">User</option>
                </select>
              </td>
              <td><UserGroupChips userId={u.id} /></td>
              <td><span className={`sdot ${u.has_matrix_card ? "ok" : ""}`} />{u.has_matrix_card ? "On" : "Off"}</td>
              <td className="text-muted-foreground">
                {locked
                  ? <><span className="sdot bad" />Locked, {u.failed_count} failed sign-ins</>
                  : formatRelativeTime(u.last_login)}
              </td>
              <td className="acts"><UserRowActions u={u} locked={locked} a={actions} /></td>
            </tr>
          );
        })}
        {empty && <tr><td colSpan={6} className="text-center text-muted-foreground">
          {showInvites ? "No invites generated this session" : "No users match"}
        </td></tr>}
      </tbody>
    </table>
  );
}
