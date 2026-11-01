export type UserRow = {
  id: string; username: string; email: string | null; role: string; is_active: boolean;
  last_login: string | null; locked_until: string | null; failed_count: number; has_matrix_card?: boolean;
};
export type UserFilter = "all" | "admins" | "locked" | "invites";

export function formatRelativeTime(iso: string | null): string {
  if (!iso) return "Never";
  const date = new Date(iso);
  const mins = Math.floor((Date.now() - date.getTime()) / 60000);
  if (mins < 1) return "Just now";
  if (mins < 60) return `${mins} min ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours} h ago`;
  const days = Math.floor(hours / 24);
  return days < 7 ? `${days} d ago` : date.toLocaleDateString();
}

export const isUserLocked = (lockedUntil: string | null) =>
  !!lockedUntil && new Date(lockedUntil) > new Date();

export function filterUsers(users: UserRow[], filter: UserFilter, query: string): UserRow[] {
  const q = query.trim().toLowerCase();
  return users.filter((u) => {
    if (filter === "invites") return false;
    if (filter === "admins" && u.role !== "admin") return false;
    if (filter === "locked" && !isUserLocked(u.locked_until)) return false;
    return !q || u.username.toLowerCase().includes(q) || (u.email ?? "").toLowerCase().includes(q);
  });
}
