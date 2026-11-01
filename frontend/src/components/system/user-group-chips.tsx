import { useQuery } from "@tanstack/react-query";
import { api } from "@/api/client";

/** Group names for one user (one small request per row; the list is admin-sized). */
export function UserGroupChips({ userId }: { userId: string }) {
  const { data: ids } = useQuery({ queryKey: ["user-groups", userId], queryFn: () => api.getUserGroups(userId) });
  const { data: groups } = useQuery({ queryKey: ["groups"], queryFn: api.listGroups });
  const names = (ids ?? []).map((id) => groups?.find((g) => g.id === id)?.name).filter(Boolean) as string[];
  if (!names.length) return <span className="text-muted-foreground">None</span>;
  return <>{names.map((n) => <span key={n} className="chip">{n}</span>)}</>;
}
