import { useCallback, useEffect, useState } from "react";
import { Copy, Monitor, RefreshCw, Trash2 } from "lucide-react";
import { api, type EnrollToken, type Workstation, type WorkstationUpdateCommand } from "@/api/client";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { ConfirmDialog } from "@/components/common/confirm-dialog";
import { WorkstationSpecs } from "@/components/system/workstation-specs";

const STATUS_STYLES: Record<string, string> = {
  online: "bg-emerald-500/15 text-emerald-400",
  offline: "bg-amber-500/15 text-amber-400",
  pending: "bg-sky-500/15 text-sky-400",
  revoked: "bg-rose-500/15 text-rose-400",
};

export function WorkstationsPanel() {
  const [rows, setRows] = useState<Workstation[]>([]);
  const [users, setUsers] = useState<{ id: string; username: string }[]>([]);
  const [enroll, setEnroll] = useState<EnrollToken | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState<"lan" | "public" | null>(null);
  const [revokeTarget, setRevokeTarget] = useState<Workstation | null>(null);
  const [purgeTarget, setPurgeTarget] = useState<Workstation | null>(null);
  const [updateCmd, setUpdateCmd] = useState<WorkstationUpdateCommand | null>(null);
  const [updCopied, setUpdCopied] = useState<"lan" | "public" | null>(null);

  const refresh = useCallback(() => {
    api.listWorkstations().then(setRows).catch((e) => setError(String(e)));
    api.listUsers().then((u) => setUsers(u.map(({ id, username }) => ({ id, username }))))
      .catch(() => {});
  }, []);
  useEffect(() => {
    refresh();
    const t = setInterval(refresh, 15000);
    return () => clearInterval(t);
  }, [refresh]);

  const mint = async () => {
    setError(null);
    try { setEnroll(await api.mintEnrollToken()); }
    catch (e) { setError(String(e)); }
  };
  const copy = async (text: string, which: "lan" | "public") => {
    await navigator.clipboard.writeText(text);
    setCopied(which);
    setTimeout(() => setCopied(null), 1500);
  };
  const openUpdate = async (ws: Workstation) => {
    setUpdateCmd(await api.workstationUpdateCommand(ws.id));
  };
  const copyUpd = async (text: string, which: "lan" | "public") => {
    await navigator.clipboard.writeText(text);
    setUpdCopied(which);
    setTimeout(() => setUpdCopied(null), 1500);
  };
  const toggleAllUsers = (ws: Workstation) =>
    api.updateWorkstation(ws.id, { all_users: !ws.all_users }).then(refresh);
  const toggleUser = (ws: Workstation, uid: string) => {
    const next = ws.allowed_user_ids.includes(uid)
      ? ws.allowed_user_ids.filter((x) => x !== uid)
      : [...ws.allowed_user_ids, uid];
    api.setWorkstationAccess(ws.id, next).then(refresh);
  };
  const handleRevoke = () => {
    if (revokeTarget) {
      api.revokeWorkstation(revokeTarget.id).then(() => {
        setRevokeTarget(null);
        refresh();
      });
    }
  };
  const handlePurge = () => {
    if (purgeTarget) {
      api.revokeWorkstation(purgeTarget.id, true).then(() => {
        setPurgeTarget(null);
        refresh();
      });
    }
  };

  return (
    <div className="space-y-6">
      <Card className="styx-card">
        <CardHeader className="pb-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="rounded-lg bg-primary/10 p-2">
                <Monitor className="h-5 w-5 text-primary" />
              </div>
              <div>
                <CardTitle>Workstations</CardTitle>
              </div>
            </div>
            <div className="flex gap-2">
              <Button
                onClick={refresh}
                variant="secondary"
                size="sm"
                title="Refresh"
              >
                <RefreshCw className="h-4 w-4" />
              </Button>
              <Button onClick={mint} size="sm">
                Enroll workstation
              </Button>
            </div>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          {error && <p className="text-sm text-rose-400">{error}</p>}

          {enroll && (
            <div className="rounded-lg border border-border bg-surface p-4 space-y-3">
              <p className="text-sm">Run this on the workstation (token valid until{" "}
                {new Date(enroll.expires_at).toLocaleString()}, single use):</p>
              {enroll.lan_command ? (
                <div className="space-y-1">
                  <p className="text-xs font-medium text-muted-foreground">
                    Same network (LAN)
                    {enroll.lan_url_source === "detected" &&
                      " — auto-detected IP; set SERVER_LAN_URL to override"}
                  </p>
                  <div className="flex items-start gap-2">
                    <code className="flex-1 break-all rounded bg-muted px-2 py-1 text-xs">
                      {enroll.lan_command}
                    </code>
                    <Button
                      onClick={() => copy(enroll.lan_command!, "lan")}
                      variant="secondary"
                      size="sm"
                      title="Copy to clipboard"
                    >
                      <Copy className="h-4 w-4" /> {copied === "lan" ? "Copied" : "Copy"}
                    </Button>
                  </div>
                </div>
              ) : (
                <p className="text-xs text-amber-400">
                  No LAN address available — set SERVER_LAN_URL on the server for
                  LAN enrollment.
                </p>
              )}
              <div className="space-y-1">
                <p className="text-xs font-medium text-muted-foreground">
                  Outside the LAN (public URL) — note: streaming still requires the
                  server to reach the workstation&apos;s IP
                </p>
                <div className="flex items-start gap-2">
                  <code className="flex-1 break-all rounded bg-muted px-2 py-1 text-xs">
                    {enroll.public_command}
                  </code>
                  <Button
                    onClick={() => copy(enroll.public_command, "public")}
                    variant="secondary"
                    size="sm"
                    title="Copy to clipboard"
                  >
                    <Copy className="h-4 w-4" /> {copied === "public" ? "Copied" : "Copy"}
                  </Button>
                </div>
              </div>
            </div>
          )}

          {rows.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              No workstations enrolled. Click "Enroll workstation" and run the command
              on a physical Linux machine on the same network.
            </p>
          ) : rows.map((ws) => {
            return (
            <div key={ws.id} className="rounded-lg border border-border bg-surface p-4 space-y-3">
              <div className="flex items-center justify-between">
                <div>
                  <span className="font-medium">{ws.name}</span>
                  <span className={`ml-2 rounded px-2 py-0.5 text-xs ${STATUS_STYLES[ws.status] ?? ""}`}>
                    {ws.status}
                  </span>
                </div>
                <div className="flex gap-2">
                  {ws.agent_outdated && (
                    <Button onClick={() => openUpdate(ws)} variant="secondary" size="sm">
                      Update
                    </Button>
                  )}
                  <Button
                    onClick={() => setRevokeTarget(ws)}
                    variant="secondary"
                    size="sm"
                    disabled={ws.status === "revoked"}
                  >
                    Revoke
                  </Button>
                  <Button
                    onClick={() => setPurgeTarget(ws)}
                    variant="destructive"
                    size="sm"
                    title="Remove from portal"
                  >
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </div>
              </div>
              <WorkstationSpecs ws={ws} />
              {ws.last_error && <p className="text-xs text-rose-400">Agent error: {ws.last_error}</p>}
              <div className="flex flex-wrap items-center gap-3 text-sm">
                <label className="flex items-center gap-1.5">
                  <input type="checkbox" checked={ws.all_users}
                         onChange={() => toggleAllUsers(ws)} />
                  All users
                </label>
                {!ws.all_users && users.map((u) => (
                  <label key={u.id} className="flex items-center gap-1.5">
                    <input type="checkbox"
                           checked={ws.allowed_user_ids.includes(u.id)}
                           onChange={() => toggleUser(ws, u.id)} />
                    {u.username}
                  </label>
                ))}
              </div>
              {ws.status === "revoked" && (
                <p className="text-xs text-muted-foreground">
                  To finish removal on the machine:{" "}
                  <code>python3 ~/.local/share/styx-agent/styx_agent.py uninstall</code>
                </p>
              )}
            </div>
            );
          })}
        </CardContent>
      </Card>

      {/* Revoke confirmation dialog */}
      <ConfirmDialog
        open={revokeTarget !== null}
        onOpenChange={(open) => !open && setRevokeTarget(null)}
        title="Revoke Workstation"
        description="The agent will stop streaming and show uninstall instructions."
        confirmLabel="Revoke"
        onConfirm={handleRevoke}
      />

      {/* Purge confirmation dialog */}
      <ConfirmDialog
        open={purgeTarget !== null}
        onOpenChange={(open) => !open && setPurgeTarget(null)}
        title={`Purge "${purgeTarget?.name ?? ""}"`}
        description="Permanently removes it from the portal. Run the uninstall on the machine too."
        variant="destructive"
        confirmLabel="Purge"
        onConfirm={handlePurge}
      />

      {/* Update agent dialog */}
      <Dialog open={updateCmd !== null} onOpenChange={(o) => { if (!o) setUpdateCmd(null); }}>
        <DialogContent className="max-w-xl">
          <DialogHeader>
            <DialogTitle>Update agent</DialogTitle>
          </DialogHeader>
          {updateCmd && (
            <div className="space-y-3 text-sm">
              <p className="text-muted-foreground">
                Run on the workstation to update {updateCmd.current_version || "—"} →{" "}
                {updateCmd.latest_version}. Restarts the agent; the desktop stays up.
              </p>
              {updateCmd.lan_command && (
                <div>
                  <p className="mb-1 text-xs text-muted-foreground">LAN</p>
                  <code className="block overflow-x-auto rounded bg-muted p-2 text-xs">
                    {updateCmd.lan_command}
                  </code>
                  <Button size="sm" variant="secondary" className="mt-1"
                          onClick={() => copyUpd(updateCmd.lan_command!, "lan")}>
                    <Copy className="h-4 w-4" /> {updCopied === "lan" ? "Copied" : "Copy"}
                  </Button>
                </div>
              )}
              <div>
                <p className="mb-1 text-xs text-muted-foreground">Public</p>
                <code className="block overflow-x-auto rounded bg-muted p-2 text-xs">
                  {updateCmd.public_command}
                </code>
                <Button size="sm" variant="secondary" className="mt-1"
                        onClick={() => copyUpd(updateCmd.public_command, "public")}>
                  <Copy className="h-4 w-4" /> {updCopied === "public" ? "Copied" : "Copy"}
                </Button>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
