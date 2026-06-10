import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { toast } from "sonner";
import { api } from "@/api/client";
import { Users, Copy, Trash2, Check, ShieldCheck, ShieldOff } from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";

export function UsersPanel() {
  const qc = useQueryClient();
  const { data: users = [] } = useQuery({
    queryKey: ["users"],
    queryFn: api.listUsers,
  });
  const [inviteUrl, setInviteUrl] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  const invite = useMutation({
    mutationFn: () => api.createInvite({ role: "user" }),
    onSuccess: (r) => setInviteUrl(`${location.origin}/accept-invite/${r.token}`),
  });

  const disable = useMutation({
    mutationFn: (id: string) => api.disableUser(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["users"] }),
  });

  const setRole = useMutation({
    mutationFn: (p: { id: string; role: string }) => api.changeRole(p.id, p.role),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["users"] }),
    onError: (e: Error) => toast.error(e.message),
  });

  const handleCopyInviteUrl = () => {
    if (inviteUrl) {
      navigator.clipboard.writeText(inviteUrl);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  return (
    <div className="space-y-6">
      <Card className="styx-card">
        <CardHeader className="pb-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="rounded-lg bg-primary/10 p-2">
                <Users className="h-5 w-5 text-primary" />
              </div>
              <div>
                <CardTitle>User management</CardTitle>
                <CardDescription>Manage users and generate invitations</CardDescription>
              </div>
            </div>
            <Button
              onClick={() => invite.mutate()}
              disabled={invite.isPending}
              size="sm"
            >
              {invite.isPending ? "Generating..." : "Generate invite"}
            </Button>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          {inviteUrl && (
            <div className="rounded-md border border-primary/40 bg-primary/5 p-3">
              <p className="text-xs font-medium">Invite link (single-use)</p>
              <div className="mt-1 flex items-center gap-2">
                <code className="flex-1 truncate text-xs">{inviteUrl}</code>
                <Button
                  size="sm"
                  variant="secondary"
                  onClick={handleCopyInviteUrl}
                  disabled={copied}
                  title="Copy to clipboard"
                  aria-label="Copy to clipboard"
                >
                  {copied ? (
                    <Check className="h-3.5 w-3.5" />
                  ) : (
                    <Copy className="h-3.5 w-3.5" />
                  )}
                </Button>
              </div>
              <p className="mt-1 text-xs text-warning">Valid for 72 hours. Share securely — anyone with this link can join.</p>
            </div>
          )}

          <div className="border border-border rounded-lg overflow-hidden">
            <table className="w-full text-sm">
              <thead className="border-b border-border bg-muted/40">
                <tr>
                  <th className="px-4 py-3 text-left font-semibold text-sm">Username</th>
                  <th className="px-4 py-3 text-left font-semibold text-sm">Role</th>
                  <th className="px-4 py-3 text-left font-semibold text-sm">Status</th>
                  <th className="px-4 py-3 text-right font-semibold text-sm">Actions</th>
                </tr>
              </thead>
              <tbody>
                {users.length === 0 ? (
                  <tr>
                    <td colSpan={4} className="px-4 py-8 text-center">
                      <div className="flex flex-col items-center gap-2">
                        <Users className="h-8 w-8 text-muted-foreground/40" />
                        <span className="text-sm text-muted-foreground">No users yet</span>
                      </div>
                    </td>
                  </tr>
                ) : (
                  users.map((u) => (
                    <tr key={u.id} className="border-b border-border hover:bg-muted/30 transition-colors">
                      <td className="px-4 py-3 font-medium">{u.username}</td>
                      <td className="px-4 py-3">
                        <span className="inline-flex items-center rounded-full bg-primary/10 px-2.5 py-1 text-xs font-medium text-primary">
                          {u.role}
                        </span>
                      </td>
                      <td className="px-4 py-3">
                        <span
                          className={`inline-flex items-center rounded-full px-2.5 py-1 text-xs font-medium ${
                            u.is_active
                              ? "bg-success/10 text-success"
                              : "bg-muted text-muted-foreground"
                          }`}
                        >
                          {u.is_active ? "Active" : "Disabled"}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-right">
                        {u.is_active && (
                          <>
                            {u.role === "admin" ? (
                              <Button
                                variant="ghost"
                                size="sm"
                                onClick={() => setRole.mutate({ id: u.id, role: "user" })}
                                disabled={setRole.isPending}
                                title="Demote to user"
                              >
                                <ShieldOff className="h-4 w-4 mr-1" />
                                Make user
                              </Button>
                            ) : (
                              <Button
                                variant="ghost"
                                size="sm"
                                onClick={() => setRole.mutate({ id: u.id, role: "admin" })}
                                disabled={setRole.isPending}
                                title="Promote to admin"
                              >
                                <ShieldCheck className="h-4 w-4 mr-1" />
                                Make admin
                              </Button>
                            )}
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => disable.mutate(u.id)}
                              disabled={disable.isPending}
                              className="text-destructive hover:text-destructive hover:bg-destructive/10"
                            >
                              <Trash2 className="h-4 w-4 mr-1" />
                              Disable
                            </Button>
                          </>
                        )}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
