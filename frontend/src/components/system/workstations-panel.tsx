import { useCallback, useEffect, useState } from "react";
import { ArrowRight, Copy, RefreshCw } from "lucide-react";
import "@/styles/admin-table.css";
import { api, type EnrollToken, type Workstation, type WorkstationUpdateCommand } from "@/api/client";
import { SectionHead } from "@/components/common/section-head";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { ConfirmDialog } from "@/components/common/confirm-dialog";
import { toast } from "sonner";
import { WorkstationRow } from "@/components/system/workstation-row";
import { WorkstationManageDialog } from "@/components/system/workstation-manage-dialog";

export function WorkstationsPanel() {
  const [rows, setRows] = useState<Workstation[]>([]);
  const [users, setUsers] = useState<{ id: string; username: string }[]>([]);
  const [enroll, setEnroll] = useState<EnrollToken | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState<"lan" | "public" | null>(null);
  const [revokeTarget, setRevokeTarget] = useState<Workstation | null>(null);
  const [purgeTarget, setPurgeTarget] = useState<Workstation | null>(null);
  const [updateCmd, setUpdateCmd] = useState<WorkstationUpdateCommand | null>(null);
  const [manageId, setManageId] = useState<string | null>(null);
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
  const requestUpdate = (ws: Workstation) =>
    api.requestAgentUpdate(ws.id).then(refresh).catch((e) => toast.error(String(e)));
  const updateAll = () =>
    api.requestAgentUpdateOutdated()
      .then((r) => { toast.success(`Update requested for ${r.requested} workstation(s)`); refresh(); })
      .catch((e) => toast.error(String(e)));
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
    <section>
      <SectionHead title="Enrolled machines" action={
        <>
          <Button onClick={refresh} variant="ghost" size="sm" title="Refresh"><RefreshCw className="h-4 w-4" /></Button>
          {rows.some((w) => w.agent_outdated && w.status === "online") && (
            <Button onClick={updateAll} variant="secondary" size="sm">Update all outdated</Button>
          )}
          <button type="button" className="btn-gold" onClick={mint}>Enroll a workstation</button>
        </>
      } />
      <div className="space-y-4">
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
            No workstations enrolled. Click "Enroll a workstation" and run the command
            on a physical Linux machine on the same network.
          </p>
        ) : rows.map((ws) => (
          <WorkstationRow key={ws.id} ws={ws} onManage={() => setManageId(ws.id)}
                          onUpdate={() => requestUpdate(ws)} onManual={() => openUpdate(ws)} />
        ))}
      </div>

      <WorkstationManageDialog ws={rows.find((w) => w.id === manageId) ?? null} users={users}
        onClose={() => setManageId(null)} onSaved={refresh} onRevoke={setRevokeTarget} onPurge={setPurgeTarget}
        onToggleAll={toggleAllUsers} onToggleUser={toggleUser} />

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
                Run on the workstation to update {updateCmd.current_version || "—"} <ArrowRight className="inline size-3.5" aria-hidden />{" "}
                {updateCmd.latest_version}. Runs a full upgrade (new engine and wheels; the previous install is kept as a fallback). The desktop session restarts.
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
    </section>
  );
}
