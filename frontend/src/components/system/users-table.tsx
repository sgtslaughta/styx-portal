import { UserRowActions, type UserActions } from "@/components/system/user-row-actions";
import { formatRelativeTime, isUserLocked, type InviteRow, type UserRow } from "@/components/system/users-filters";

type Props = {
  users: UserRow[];
  invites: InviteRow[];
  showInvites: boolean;
  actions: UserActions;
  selfId?: string;
  selected: Set<string>;
  toggle: (id: string) => void;
  toggleAll: (ids: string[]) => void;
  setRole: (id: string, role: string) => void;
};

const dim = "text-muted-foreground";

export function UsersTable({ users, invites, showInvites, actions, selfId, selected, toggle, toggleAll, setRole }: Props) {
  const empty = showInvites ? invites.length === 0 : users.length === 0;
  const ids = users.map((u) => u.id);
  const allOn = ids.length > 0 && ids.every((id) => selected.has(id));
  return (
    <table className="dense full users-table">
      <thead>
        <tr>
          <th>{!showInvites && (
            <input type="checkbox" aria-label="Select all users" checked={allOn} onChange={() => toggleAll(ids)} />
          )}</th>
          <th>Name</th><th>Role</th><th>Groups</th><th>Sign-in card</th><th>Last sign-in</th><th />
        </tr>
      </thead>
      <tbody>
        {showInvites && invites.map((i) => (
          <tr key={i.id}>
            <td />
            <td><strong>{i.email || "Invite link"}</strong>
              <small>Sent {new Date(i.created_at).toLocaleDateString()}</small></td>
            <td className={dim}>{i.role === "admin" ? "Admin" : "User"}</td><td className={dim}>None</td>
            <td className={dim}>Not set</td><td className={dim}>Invite pending</td>
            <td className="acts" />
          </tr>
        ))}
        {!showInvites && users.map((u) => {
          const locked = isUserLocked(u.locked_until);
          const self = u.id === selfId;
          return (
            <tr key={u.id} className={locked ? "warn" : undefined}>
              <td><input type="checkbox" aria-label={`Select ${u.username}`} checked={selected.has(u.id)}
                         onChange={() => toggle(u.id)} /></td>
              <td>
                <strong>{u.username}</strong>
                <small>{u.email || (u.is_active ? "" : "Disabled")}</small>
              </td>
              <td>
                <select aria-label={`Role for ${u.username}`} value={u.role} disabled={!u.is_active || self}
                        title={self ? "You can't change your own role" : undefined}
                        onChange={(e) => setRole(u.id, e.target.value)}>
                  <option value="admin">Admin</option><option value="user">User</option>
                </select>
              </td>
              <td>{u.groups?.length ? u.groups.map((n) => <span key={n} className="chip">{n}</span>) : <span className={dim}>None</span>}</td>
              <td><span className={`sdot ${u.has_matrix_card ? "ok" : ""}`} />{u.has_matrix_card ? "On" : "Off"}</td>
              <td className={dim}>
                {locked
                  ? <><span className="sdot bad" />Locked, {u.failed_count} failed sign-ins</>
                  : formatRelativeTime(u.last_login)}
              </td>
              <td className="acts"><UserRowActions u={u} locked={locked} a={actions} self={self} /></td>
            </tr>
          );
        })}
        {empty && <tr><td colSpan={7} className="text-center text-muted-foreground">
          {showInvites ? "No pending invites" : "No users match"}
        </td></tr>}
      </tbody>
    </table>
  );
}
