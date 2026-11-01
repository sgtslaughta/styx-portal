import { useRef, useState } from "react";
import { ChevronLeft, X } from "lucide-react";
import { toast } from "sonner";
import { Drawer, DrawerContent, DrawerDescription, DrawerTitle } from "@/components/ui/drawer";
import { TemplateBuilderModal } from "@/components/templates/template-builder-modal";
import { useWaveTransition } from "@/components/effects/transition-provider";
import { useAuth } from "@/hooks/use-auth";
import { useCreateInstance, useInstances } from "@/hooks/use-instances";
import { useTemplates } from "@/hooks/use-templates";
import { profileMountOf } from "@/lib/profiles";
import { slugify } from "@/lib/utils";
import { CatalogGrid } from "./catalog-grid";
import { LaunchStep, type LaunchTarget } from "./launch-step";
import type { ServiceTemplate } from "@/lib/types";

export function NewContainerDrawer({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [target, setTarget] = useState<LaunchTarget | null>(null);
  const [editing, setEditing] = useState<ServiceTemplate | null>(null);
  const searchRef = useRef<HTMLInputElement>(null);
  const returnTo = useRef<HTMLElement | null>(null);
  const { user } = useAuth();
  const { data: setups = [] } = useTemplates({ shared: true });
  const { data: instances = [] } = useInstances();
  const create = useCreateInstance();
  const wave = useWaveTransition();

  function close() { setTarget(null); onClose(); }

  /** One-click launch: setup defaults, name and address de-duplicated with a numeric suffix. */
  async function quickLaunch(t: ServiceTemplate) {
    const names = new Set(instances.map((i) => i.name));
    const subs = new Set(instances.map((i) => i.subdomain));
    let n = 1, name = t.display_name, sub = slugify(name);
    while (names.has(name) || subs.has(sub)) { n++; name = `${t.display_name} ${n}`; sub = slugify(name); }
    try {
      await create.mutateAsync({
        template_id: t.id, name, subdomain: sub,
        use_profile: !!profileMountOf(t.profile_mount, t.volumes), use_gpu: true,
        // The setup's own idle policy wins; stop-after-30-min only when it saved none.
        session_config: Object.keys(t.session_config ?? {}).length
          ? t.session_config
          : { timeout_action: "stop", never_timeout: false, idle_timeout: "30m" },
      });
      close();
      wave.play(`Launching ${name}…`);
      toast.success(`Instance "${name}" launched!`);
    } catch (e) {
      toast.error(`Launch failed: ${(e as Error).message}`);
    }
  }

  const title = target ? `Launch ${target.image?.name ?? target.template?.display_name ?? target.custom?.split("/").pop()?.replace(/[:@].*$/, "")}` : "New container";

  return (
    <>
      <Drawer open={open} onOpenChange={(v) => !v && close()}>
        <DrawerContent
          showCloseButton={false}
          aria-describedby={undefined}
          onOpenAutoFocus={(e) => { e.preventDefault(); returnTo.current = document.activeElement as HTMLElement | null; searchRef.current?.focus(); }}
          onCloseAutoFocus={(e) => { e.preventDefault(); returnTo.current?.focus(); }}
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
              <CatalogGrid setups={setups} searchRef={searchRef} isAdmin={user?.role === "admin"}
                onPickImage={(image) => setTarget({ image })} onPickSetup={(template) => setTarget({ template })}
                onLaunchSetup={quickLaunch} onEditSetup={setEditing} onCustom={(custom) => setTarget({ custom })} />
            </div>
          )}
        </DrawerContent>
      </Drawer>
      {editing && <TemplateBuilderModal open mode="edit" template={editing} onClose={() => setEditing(null)} />}
    </>
  );
}
