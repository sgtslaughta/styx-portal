import { useState } from "react";
import { api, ApiError, type OpenMode, type Workstation } from "@/api/client";
import { ConfirmDialog } from "@/components/common/confirm-dialog";
import { useOpenChoice } from "@/components/open-prompt";
import { openPending } from "@/lib/connect-wipe";
import { writeRecent } from "@/lib/workspace";

type Ask = { ws: Workstation; mode?: OpenMode };

/** Connect / Reconnect / Join for workstations. Render `dialog` once next to the buttons.
 *  `mode` skips the open-preference prompt (e.g. "Open in new tab"). */
export function useWorkstationConnect() {
  const choose = useOpenChoice();
  const [ask, setAsk] = useState<Ask | null>(null);
  const [error, setError] = useState<string | null>(null);

  function open(ws: Workstation, force: boolean, mode?: OpenMode) {
    setError(null);
    writeRecent({ kind: "workstation", id: ws.id });
    const run = (m: OpenMode) => {
      openPending(m, `Connecting to ${ws.name}…`, async () => (await api.workstationConnectUrl(ws.id, force)).url)
        .catch((e: unknown) => {
          if (e instanceof ApiError && e.status === 423) setAsk({ ws, mode }); // raced: someone joined meanwhile
          else setError((e as Error).message);
        });
    };
    if (mode) run(mode);
    else choose("workspaces", ws.name, run);
  }

  const connect = (ws: Workstation, mode?: OpenMode) =>
    ws.in_use && !ws.in_use_self ? setAsk({ ws, mode }) : open(ws, false, mode);

  const dialog = (
    <ConfirmDialog
      open={ask !== null}
      onOpenChange={(o) => { if (!o) setAsk(null); }}
      title={`Join "${ask?.ws.name ?? ""}"?`}
      description={`This workstation is in use by ${ask?.ws.in_use_by ?? "another user"}. Joining shares the same desktop — you will both see and control the same screen.`}
      confirmLabel="Join"
      variant="default"
      onConfirm={() => {
        if (!ask) return;
        setAsk(null);
        open(ask.ws, true, ask.mode);
      }}
    />
  );
  return { connect, dialog, error };
}
