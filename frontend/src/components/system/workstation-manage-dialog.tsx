import { Trash2 } from "lucide-react";
import type { Workstation } from "@/api/client";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { WorkstationIcon } from "@/components/system/workstation-icon";
import { WorkstationIconSettings } from "@/components/system/workstation-icon-settings";
import { WorkstationSpecs } from "@/components/system/workstation-specs";
import { WorkstationStreamSettings } from "@/components/system/workstation-stream-settings";

type Props = {
  ws: Workstation | null;
  users: { id: string; username: string }[];
  onClose: () => void;
  onSaved: () => void;
  onRevoke: (ws: Workstation) => void;
  onPurge: (ws: Workstation) => void;
  onToggleAll: (ws: Workstation) => void;
  onToggleUser: (ws: Workstation, uid: string) => void;
};

export function WorkstationManageDialog({ ws, users, onClose, onSaved, onRevoke, onPurge, onToggleAll, onToggleUser }: Props) {
  return (
    <Dialog open={ws !== null} onOpenChange={(o) => { if (!o) onClose(); }}>
      <DialogContent className="max-h-[85vh] max-w-3xl overflow-y-auto">
        {ws && (
          <>
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2">
                <WorkstationIcon ws={ws} />{ws.name}
              </DialogTitle>
            </DialogHeader>
            <div className="space-y-3">
              <WorkstationSpecs ws={ws} />
              <WorkstationIconSettings ws={ws} onSaved={onSaved} />
              <WorkstationStreamSettings ws={ws} onSaved={onSaved} />
              {ws.last_error && <p className="text-xs text-rose-400">Agent error: {ws.last_error}</p>}
              <div className="flex flex-wrap items-center gap-3 text-sm">
                <label className="flex items-center gap-1.5">
                  <input type="checkbox" checked={ws.all_users} onChange={() => onToggleAll(ws)} />
                  All users
                </label>
                {!ws.all_users && users.map((u) => (
                  <label key={u.id} className="flex items-center gap-1.5">
                    <input type="checkbox" checked={ws.allowed_user_ids.includes(u.id)}
                           onChange={() => onToggleUser(ws, u.id)} />
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
              <div className="flex gap-2">
                <Button onClick={() => onRevoke(ws)} variant="secondary" size="sm" disabled={ws.status === "revoked"}>
                  Revoke
                </Button>
                <Button onClick={() => onPurge(ws)} variant="destructive" size="sm" title="Remove from portal">
                  <Trash2 className="h-4 w-4" /> Remove
                </Button>
              </div>
            </div>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}
