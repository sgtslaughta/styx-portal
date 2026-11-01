import { useState, type ReactNode } from "react";
import { toast } from "sonner";
import { api, ApiError, type Workstation } from "@/api/client";
import { ConfirmDialog } from "@/components/common/confirm-dialog";
import { useOpenChoice } from "@/components/open-prompt";
import { openPending } from "@/lib/connect-wipe";
import { recordOpened } from "@/lib/recents";
import type { Instance } from "@/lib/types";

/** Workstation connect flow (takeover confirm on a busy desktop, 423 race, open-mode choice). Render `dialog` once. */
export function useWorkstationConnect(): {
  connect: (ws: Workstation, force?: boolean) => void;
  error: string | null;
  dialog: ReactNode;
} {
  const [takeover, setTakeover] = useState<Workstation | null>(null);
  const [error, setError] = useState<string | null>(null);
  const choose = useOpenChoice();

  const connect = (ws: Workstation, force = false) => {
    setError(null);
    // Takeover is confirmed here, in this tab, before any new tab opens.
    if (!force && ws.in_use && !ws.in_use_self) { setTakeover(ws); return; }
    choose("workspaces", ws.name, (mode) => {
      recordOpened(ws.id);
      openPending(mode, `Connecting to ${ws.name}…`, async () => (await api.workstationConnectUrl(ws.id, force)).url)
        .catch((e) => {
          if (e instanceof ApiError && e.status === 423) setTakeover(ws); // raced: someone joined meanwhile
          else setError((e as Error).message);
        });
    });
  };

  const dialog = (
    <ConfirmDialog
      open={takeover !== null}
      onOpenChange={(open) => !open && setTakeover(null)}
      title={`Take over "${takeover?.name ?? ""}"?`}
      description={`This workstation is in use by ${takeover?.in_use_by ?? "another user"}. Joining shares the same desktop — you will both see and control the same screen.`}
      confirmLabel="Take over"
      variant="destructive"
      onConfirm={() => {
        if (takeover) { connect(takeover, true); setTakeover(null); }
      }}
    />
  );
  return { connect, error, dialog };
}

/** Open a running container's desktop, honouring the user's open-mode preference. */
export function useOpenInstance(): (inst: Instance) => void {
  const choose = useOpenChoice();
  return (inst) =>
    choose("workspaces", inst.name, (mode) => {
      recordOpened(inst.id);
      openPending(mode, `Launching ${inst.name}…`, async () => `/desktop/${inst.subdomain}`)
        .catch((e: Error) => toast.error(`Connect failed: ${e.message}`));
    });
}
