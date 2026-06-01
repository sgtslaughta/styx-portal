import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "@/api/client";
import { Users, Copy, Trash2 } from "lucide-react";

export function UsersPanel() {
  const qc = useQueryClient();
  const { data: users = [] } = useQuery({
    queryKey: ["users"],
    queryFn: api.listUsers,
  });
  const [inviteUrl, setInviteUrl] = useState<string | null>(null);

  const invite = useMutation({
    mutationFn: () => api.createInvite({ role: "user" }),
    onSuccess: (r) => setInviteUrl(`${location.origin}/accept-invite/${r.token}`),
  });

  const disable = useMutation({
    mutationFn: (id: string) => api.disableUser(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["users"] }),
  });

  const handleCopyInviteUrl = () => {
    if (inviteUrl) {
      navigator.clipboard.writeText(inviteUrl);
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Users className="h-5 w-5 text-muted-foreground" />
          <h2 className="text-lg font-semibold">Users</h2>
        </div>
        <button
          className="rounded bg-blue-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-blue-700 transition-colors disabled:opacity-50"
          onClick={() => invite.mutate()}
          disabled={invite.isPending}
        >
          {invite.isPending ? "Generating..." : "Generate invite"}
        </button>
      </div>

      {inviteUrl && (
        <div className="rounded border border-green-200 bg-green-50 dark:border-green-900 dark:bg-green-950 p-3 text-sm">
          <div className="mb-2 text-sm text-gray-600 dark:text-gray-300">
            Invite link (single-use, 72h):
          </div>
          <div className="flex items-center gap-2">
            <code className="flex-1 break-all rounded bg-white dark:bg-gray-900 px-2 py-1 font-mono text-xs">
              {inviteUrl}
            </code>
            <button
              onClick={handleCopyInviteUrl}
              className="rounded p-1.5 hover:bg-white/50 dark:hover:bg-gray-800 transition-colors"
              title="Copy to clipboard"
            >
              <Copy className="h-4 w-4" />
            </button>
          </div>
        </div>
      )}

      <div className="overflow-x-auto rounded border border-border">
        <table className="w-full text-sm">
          <thead className="border-b border-border bg-muted/50">
            <tr>
              <th className="px-4 py-2 text-left font-semibold">Username</th>
              <th className="px-4 py-2 text-left font-semibold">Email</th>
              <th className="px-4 py-2 text-left font-semibold">Role</th>
              <th className="px-4 py-2 text-left font-semibold">Status</th>
              <th className="px-4 py-2 text-right font-semibold">Actions</th>
            </tr>
          </thead>
          <tbody>
            {users.length === 0 ? (
              <tr>
                <td colSpan={5} className="px-4 py-4 text-center text-muted-foreground">
                  No users yet
                </td>
              </tr>
            ) : (
              users.map((u) => (
                <tr key={u.id} className="border-b border-border hover:bg-muted/30 transition-colors">
                  <td className="px-4 py-2 font-medium">{u.username}</td>
                  <td className="px-4 py-2 text-muted-foreground">{u.email || "—"}</td>
                  <td className="px-4 py-2">
                    <span className="inline-flex rounded-full bg-blue-100 dark:bg-blue-900 px-2.5 py-0.5 text-xs font-medium text-blue-800 dark:text-blue-200">
                      {u.role}
                    </span>
                  </td>
                  <td className="px-4 py-2">
                    <span
                      className={`inline-flex rounded-full px-2.5 py-0.5 text-xs font-medium ${
                        u.is_active
                          ? "bg-green-100 dark:bg-green-900 text-green-800 dark:text-green-200"
                          : "bg-red-100 dark:bg-red-900 text-red-800 dark:text-red-200"
                      }`}
                    >
                      {u.is_active ? "Active" : "Disabled"}
                    </span>
                  </td>
                  <td className="px-4 py-2 text-right">
                    {u.is_active && (
                      <button
                        className="inline-flex items-center gap-1 rounded px-2 py-1 text-red-500 hover:bg-red-50 dark:hover:bg-red-950 transition-colors disabled:opacity-50"
                        onClick={() => disable.mutate(u.id)}
                        disabled={disable.isPending}
                        title="Disable user"
                      >
                        <Trash2 className="h-4 w-4" />
                        <span className="text-xs">Disable</span>
                      </button>
                    )}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
