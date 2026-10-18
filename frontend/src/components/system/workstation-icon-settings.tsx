import { api, type Workstation } from "@/api/client";
import { IconSettings } from "@/components/system/icon-settings";

export { emojiError, MAX_IMAGE_BYTES } from "@/components/system/icon-settings";

export function WorkstationIconSettings({ ws, onSaved }: { ws: Workstation; onSaved: () => void }) {
  return (
    <IconSettings
      id={ws.id}
      kind={ws.icon_kind}
      iconUrl={`/api/workstations/${ws.id}/icon?v=${ws.icon_etag}`}
      onSave={async (kind, value) => {
        await api.setWorkstationIcon(ws.id, kind, value);
        onSaved();
      }}
    />
  );
}
