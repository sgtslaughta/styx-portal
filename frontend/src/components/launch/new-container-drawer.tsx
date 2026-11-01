import { useRef, useState } from "react";
import { ChevronLeft, X } from "lucide-react";
import { Drawer, DrawerContent, DrawerDescription, DrawerTitle } from "@/components/ui/drawer";
import { useTemplates } from "@/hooks/use-templates";
import { CatalogGrid } from "./catalog-grid";
import { LaunchStep, type LaunchTarget } from "./launch-step";

export function NewContainerDrawer({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [target, setTarget] = useState<LaunchTarget | null>(null);
  const searchRef = useRef<HTMLInputElement>(null);
  const { data: setups = [] } = useTemplates({ shared: true });

  function close() { setTarget(null); onClose(); }
  const title = target ? `Launch ${target.image?.name ?? target.template?.display_name ?? target.custom?.split("/").pop()}` : "New container";

  return (
    <Drawer open={open} onOpenChange={(v) => !v && close()}>
      <DrawerContent
        showCloseButton={false}
        aria-describedby={undefined}
        onOpenAutoFocus={(e) => { e.preventDefault(); searchRef.current?.focus(); }}
        className="w-[min(760px,100vw)] max-w-none min-w-0 bg-background dark:bg-background motion-reduce:animate-none motion-reduce:duration-0"
      >
        <div className="flex items-center gap-3 border-b border-border px-6 py-[18px]">
          {target && (
            <button type="button" aria-label="Back to catalog" onClick={() => setTarget(null)} className="inline-flex items-center rounded-md px-1.5 py-1 text-sm text-muted-foreground hover:text-foreground"><ChevronLeft className="size-4" aria-hidden />Back</button>
          )}
          <DrawerTitle className="flex-1 text-[19px]">{title}</DrawerTitle>
          <DrawerDescription className="sr-only">Pick an image, then choose a size and launch.</DrawerDescription>
          <button type="button" aria-label="Close" onClick={close} className="rounded-md p-1.5 text-muted-foreground hover:text-foreground"><X className="size-4" aria-hidden /></button>
        </div>
        {target ? (
          <LaunchStep key={target.image?.name ?? target.template?.id ?? target.custom} target={target} onClose={close} />
        ) : (
          <div className="flex-1 overflow-y-auto px-6 py-5">
            <CatalogGrid setups={setups} searchRef={searchRef} onPickImage={(image) => setTarget({ image })} onPickSetup={(template) => setTarget({ template })} onCustom={(custom) => setTarget({ custom })} />
          </div>
        )}
      </DrawerContent>
    </Drawer>
  );
}
