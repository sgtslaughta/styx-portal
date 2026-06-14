import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { toast } from "sonner";
import { api, ApiError } from "@/api/client";
import { Users, Copy, Trash2, Check, ShieldCheck, ShieldOff, Lock, Unlock, RefreshCw, AlertTriangle, X } from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
  DropdownMenuSeparator,
} from "@/components/ui/dropdown-menu";

type User = {
  id: string;
  username: string;
  email: string | null;
  role: string;
  is_active: boolean;
  last_login: string | null;
  locked_until: string | null;
  failed_count: number;
};

function formatRelativeTime(isoString: string | null): string {
  if (!isoString) return "—";
  const date = new Date(isoString);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffSecs = Math.floor(diffMs / 1000);
  const diffMins = Math.floor(diffSecs / 60);
  const diffHours = Math.floor(diffMins / 60);
  const diffDays = Math.floor(diffHours / 24);

  if (diffSecs < 60) return "just now";
  if (diffMins < 60) return `${diffMins}m ago`;
  if (diffHours < 24) return `${diffHours}h ago`;
  if (diffDays < 7) return `${diffDays}d ago`;
  return date.toLocaleDateString();
}

function isUserLocked(lockedUntil: string | null): boolean {
  if (!lockedUntil) return false;
  const lockDate = new Date(lockedUntil);
  return lockDate > new Date();
}

export function UsersPanel() {
  const qc = useQueryClient();
  const { data: users = [] } = useQuery({
    queryKey: ["users"],
    queryFn: api.listUsers,
  });

  const [inviteUrl, setInviteUrl] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [resetPasswordDialog, setResetPasswordDialog] = useState<{ userId: string; tempPassword: string } | null>(null);
  const [resetPasswordCopied, setResetPasswordCopied] = useState(false);
  const [deleteConfirmDialog, setDeleteConfirmDialog] = useState<string | null>(null);

  const invite = useMutation({
    mutationFn: () => api.createInvite({ role: "user" }),
    onSuccess: (r) => setInviteUrl(`${location.origin}/accept-invite/${r.token}`),
  });

  const disable = useMutation({
    mutationFn: (id: string) => api.disableUser(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["users"] }),
    onError: (e: Error) => toast.error(e.message),
  });

  const setRole = useMutation({
    mutationFn: (p: { id: string; role: string }) => api.changeRole(p.id, p.role),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["users"] }),
    onError: (e: Error) => toast.error(e.message),
  });

  const unlock = useMutation({
    mutationFn: (id: string) => api.unlockUser(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["users"] });
      toast.success("User unlocked");
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const resetPassword = useMutation({
    mutationFn: (id: string) => api.resetUserPassword(id),
    onSuccess: (data, userId) => {
      setResetPasswordDialog({ userId, tempPassword: data.temp_password });
      qc.invalidateQueries({ queryKey: ["users"] });
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const forcePasswordChange = useMutation({
    mutationFn: (id: string) => api.forcePasswordChange(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["users"] });
      toast.success("User forced to change password");
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const deleteUser = useMutation({
    mutationFn: (id: string) => api.deleteUser(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["users"] });
      toast.success("User deleted");
      setDeleteConfirmDialog(null);
    },
    onError: (e: Error) => {
      const error = e as ApiError;
      toast.error(error.message);
    },
  });

  const handleCopyInviteUrl = () => {
    if (inviteUrl) {
      navigator.clipboard.writeText(inviteUrl);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  const handleCopyTempPassword = () => {
    if (resetPasswordDialog) {
      navigator.clipboard.writeText(resetPasswordDialog.tempPassword);
      setResetPasswordCopied(true);
      setTimeout(() => setResetPasswordCopied(false), 2000);
    }
  };

  const targetUser = users.find((u) => u.id === deleteConfirmDialog);

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
                  <th className="px-4 py-3 text-left font-semibold text-sm">Last login</th>
                  <th className="px-4 py-3 text-right font-semibold text-sm">Actions</th>
                </tr>
              </thead>
              <tbody>
                {users.length === 0 ? (
                  <tr>
                    <td colSpan={5} className="px-4 py-8 text-center">
                      <div className="flex flex-col items-center gap-2">
                        <Users className="h-8 w-8 text-muted-foreground/40" />
                        <span className="text-sm text-muted-foreground">No users yet</span>
                      </div>
                    </td>
                  </tr>
                ) : (
                  users.map((u) => {
                    const isLocked = isUserLocked(u.locked_until);
                    return (
                      <tr key={u.id} className="border-b border-border hover:bg-muted/30 transition-colors">
                        <td className="px-4 py-3 font-medium">{u.username}</td>
                        <td className="px-4 py-3">
                          <span className="inline-flex items-center rounded-full bg-primary/10 px-2.5 py-1 text-xs font-medium text-primary">
                            {u.role}
                          </span>
                        </td>
                        <td className="px-4 py-3">
                          <div className="flex items-center gap-2">
                            {isLocked ? (
                              <div className="flex items-center gap-2">
                                <span className="inline-flex items-center rounded-full bg-destructive/10 px-2.5 py-1 text-xs font-medium text-destructive">
                                  <Lock className="h-3 w-3 mr-1" />
                                  Locked
                                </span>
                              </div>
                            ) : (
                              <span
                                className={`inline-flex items-center rounded-full px-2.5 py-1 text-xs font-medium ${
                                  u.is_active
                                    ? "bg-success/10 text-success"
                                    : "bg-muted text-muted-foreground"
                                }`}
                              >
                                {u.is_active ? "Active" : "Disabled"}
                              </span>
                            )}
                          </div>
                        </td>
                        <td className="px-4 py-3 text-xs text-muted-foreground">
                          {formatRelativeTime(u.last_login)}
                        </td>
                        <td className="px-4 py-3 text-right">
                          {isLocked && (
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => unlock.mutate(u.id)}
                              disabled={unlock.isPending}
                              title="Unlock user account"
                              className="text-success hover:text-success hover:bg-success/10"
                            >
                              <Unlock className="h-4 w-4 mr-1" />
                              Unlock
                            </Button>
                          )}
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

                              <DropdownMenu>
                                <DropdownMenuTrigger asChild>
                                  <Button
                                    variant="ghost"
                                    size="sm"
                                    disabled={
                                      resetPassword.isPending ||
                                      forcePasswordChange.isPending ||
                                      deleteUser.isPending
                                    }
                                  >
                                    More
                                  </Button>
                                </DropdownMenuTrigger>
                                <DropdownMenuContent align="end">
                                  <DropdownMenuItem
                                    onClick={() => resetPassword.mutate(u.id)}
                                    disabled={resetPassword.isPending}
                                  >
                                    <RefreshCw className="h-4 w-4 mr-2" />
                                    Reset password
                                  </DropdownMenuItem>
                                  <DropdownMenuItem
                                    onClick={() => forcePasswordChange.mutate(u.id)}
                                    disabled={forcePasswordChange.isPending}
                                  >
                                    <AlertTriangle className="h-4 w-4 mr-2" />
                                    Force password change
                                  </DropdownMenuItem>
                                  <DropdownMenuSeparator />
                                  <DropdownMenuItem
                                    onClick={() => disable.mutate(u.id)}
                                    disabled={disable.isPending}
                                  >
                                    <Trash2 className="h-4 w-4 mr-2" />
                                    Disable
                                  </DropdownMenuItem>
                                  <DropdownMenuItem
                                    onClick={() => setDeleteConfirmDialog(u.id)}
                                    disabled={deleteUser.isPending}
                                    className="text-destructive focus:text-destructive"
                                  >
                                    <Trash2 className="h-4 w-4 mr-2" />
                                    Delete permanently
                                  </DropdownMenuItem>
                                </DropdownMenuContent>
                              </DropdownMenu>
                            </>
                          )}
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>

      {/* Reset password dialog */}
      <Dialog open={!!resetPasswordDialog} onOpenChange={(open) => !open && setResetPasswordDialog(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Temporary Password</DialogTitle>
            <DialogDescription>
              Share this one-time password with the user. They must change it on their next login.
            </DialogDescription>
          </DialogHeader>
          {resetPasswordDialog && (
            <div className="space-y-4">
              <div className="rounded-md border border-border bg-muted/40 p-4">
                <p className="text-xs font-medium text-muted-foreground mb-2">Temporary password:</p>
                <div className="flex items-center gap-2">
                  <code className="flex-1 break-all font-mono text-sm font-medium bg-background rounded px-3 py-2 select-all">
                    {resetPasswordDialog.tempPassword}
                  </code>
                  <Button
                    size="sm"
                    variant="secondary"
                    onClick={handleCopyTempPassword}
                    disabled={resetPasswordCopied}
                    title="Copy to clipboard"
                  >
                    {resetPasswordCopied ? (
                      <Check className="h-4 w-4" />
                    ) : (
                      <Copy className="h-4 w-4" />
                    )}
                  </Button>
                </div>
              </div>
              <div className="rounded-md border border-amber-200/50 bg-amber-50/50 dark:border-amber-900/30 dark:bg-amber-950/20 p-3">
                <p className="text-xs text-amber-900 dark:text-amber-200">
                  Store this securely. You cannot retrieve it again. The user must use it to log in next.
                </p>
              </div>
              <Button onClick={() => setResetPasswordDialog(null)} className="w-full">
                Done
              </Button>
            </div>
          )}
        </DialogContent>
      </Dialog>

      {/* Delete confirmation dialog */}
      <Dialog open={!!deleteConfirmDialog} onOpenChange={(open) => !open && setDeleteConfirmDialog(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 text-destructive">
              <AlertTriangle className="h-5 w-5" />
              Delete user permanently?
            </DialogTitle>
            <DialogDescription>
              {targetUser ? (
                <>
                  This will permanently delete <strong>{targetUser.username}</strong>. This action cannot be undone.
                </>
              ) : null}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div className="rounded-md border border-destructive/20 bg-destructive/5 p-3">
              <p className="text-xs text-destructive font-medium">
                The user must not own any instances or templates. If they do, assign or delete them first.
              </p>
            </div>
            <div className="flex gap-2 justify-end">
              <Button
                variant="outline"
                onClick={() => setDeleteConfirmDialog(null)}
                disabled={deleteUser.isPending}
              >
                Cancel
              </Button>
              <Button
                variant="destructive"
                onClick={() => deleteConfirmDialog && deleteUser.mutate(deleteConfirmDialog)}
                disabled={deleteUser.isPending}
              >
                {deleteUser.isPending ? (
                  <>
                    <Trash2 className="h-4 w-4 mr-2 animate-pulse" />
                    Deleting…
                  </>
                ) : (
                  <>
                    <Trash2 className="h-4 w-4 mr-2" />
                    Delete
                  </>
                )}
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
