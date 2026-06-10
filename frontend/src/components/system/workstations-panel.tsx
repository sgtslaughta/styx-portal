import { useCallback, useEffect, useState } from "react";
import { Copy, Monitor, RefreshCw, Trash2 } from "lucide-react";
import { api, type EnrollToken, type Workstation } from "@/api/client";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";

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
  const [copied, setCopied] = useState(false);

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
  const copy = async (text: string) => {
    await navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };
  const toggleAllUsers = (ws: Workstation) =>
    api.updateWorkstation(ws.id, { all_users: !ws.all_users }).then(refresh);
  const toggleUser = (ws: Workstation, uid: string) => {
    const next = ws.allowed_user_ids.includes(uid)
      ? ws.allowed_user_ids.filter((x) => x !== uid)
      : [...ws.allowed_user_ids, uid];
    api.setWorkstationAccess(ws.id, next).then(refresh);
  };
  const revoke = (ws: Workstation) => {
    if (!confirm(`Revoke "${ws.name}"? The agent will stop streaming and show uninstall instructions.`)) return;
    api.revokeWorkstation(ws.id).then(refresh);
  };
  const purge = (ws: Workstation) => {
    if (!confirm(`Permanently remove "${ws.name}" from the portal? Run the uninstall on the machine too.`)) return;
    api.revokeWorkstation(ws.id, true).then(refresh);
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
            <div className="rounded-lg border border-border bg-surface p-4 space-y-2">
              <p className="text-sm">Run this on the workstation (token valid until{" "}
                {new Date(enroll.expires_at).toLocaleString()}, single use):</p>
              <div className="flex items-start gap-2">
                <code className="flex-1 break-all rounded bg-muted px-2 py-1 text-xs">
                  {enroll.command}
                </code>
                <Button
                  onClick={() => copy(enroll.command)}
                  variant="secondary"
                  size="sm"
                  title="Copy to clipboard"
                >
                  <Copy className="h-4 w-4" /> {copied ? "Copied" : "Copy"}
                </Button>
              </div>
            </div>
          )}

          {rows.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              No workstations enrolled. Click "Enroll workstation" and run the command
              on a physical Linux machine on the same network.
            </p>
          ) : rows.map((ws) => (
            <div key={ws.id} className="rounded-lg border border-border bg-surface p-4 space-y-3">
              <div className="flex items-center justify-between">
                <div>
                  <span className="font-medium">{ws.name}</span>
                  <span className={`ml-2 rounded px-2 py-0.5 text-xs ${STATUS_STYLES[ws.status] ?? ""}`}>
                    {ws.status}
                  </span>
                </div>
                <div className="flex gap-2">
                  <Button
                    onClick={() => revoke(ws)}
                    variant="secondary"
                    size="sm"
                    disabled={ws.status === "revoked"}
                  >
                    Revoke
                  </Button>
                  <Button
                    onClick={() => purge(ws)}
                    variant="destructive"
                    size="sm"
                    title="Remove from portal"
                  >
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </div>
              </div>
              <dl className="grid grid-cols-2 gap-x-6 gap-y-1 text-xs text-muted-foreground sm:grid-cols-4">
                <div><dt className="inline">IP: </dt><dd className="inline">{ws.lan_ip}:{ws.port}</dd></div>
                <div><dt className="inline">Display: </dt><dd className="inline">{ws.display_server}</dd></div>
                <div><dt className="inline">GPU: </dt><dd className="inline">{String(ws.gpu_info?.vendor ?? "none")}</dd></div>
                <div><dt className="inline">Last seen: </dt>
                  <dd className="inline">{ws.last_heartbeat ? new Date(ws.last_heartbeat).toLocaleTimeString() : "never"}</dd></div>
              </dl>
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
          ))}
        </CardContent>
      </Card>
    </div>
  );
}
