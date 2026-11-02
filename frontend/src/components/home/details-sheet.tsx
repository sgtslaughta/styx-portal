import { Drawer, DrawerContent, DrawerTitle } from "@/components/ui/drawer";
import { InstanceDetailPane } from "@/components/instances/instance-detail-pane";
import { WorkstationPreview } from "@/components/instances/workstation-list";
import type { Workstation } from "@/api/client";

export type Detail = { kind: "desktop"; ws: Workstation } | { kind: "container"; id: string; name: string };

/** Right-hand sheet hosting the existing detail panes (edit, recreate, keepalive, actions). */
export function DetailsSheet({ detail, onClose }: { detail: Detail | null; onClose: () => void }) {
  return (
    <Drawer open={detail !== null} onOpenChange={(o) => !o && onClose()}>
      <DrawerContent className="w-screen max-w-none md:w-[min(560px,100vw)] md:[@media(min-height:501px)]:w-[min(560px,100vw)]">
        <DrawerTitle className="sr-only">{detail ? `${detail.kind === "desktop" ? detail.ws.name : detail.name} details` : "Details"}</DrawerTitle>
        <div className="min-h-0 flex-1 overflow-y-auto pt-10">
          {detail?.kind === "desktop" && <WorkstationPreview key={detail.ws.id} ws={detail.ws} />}
          {detail?.kind === "container" && <InstanceDetailPane key={detail.id} instanceId={detail.id} />}
        </div>
      </DrawerContent>
    </Drawer>
  );
}
