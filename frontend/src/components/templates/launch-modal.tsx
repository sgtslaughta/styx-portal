import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { useCreateTemplate, useUpdateTemplate } from "@/hooks/use-templates";
import { useCreateInstance } from "@/hooks/use-instances";
import { useGpuInfo } from "@/hooks/use-gpu";
import { useLaunchConfig } from "@/hooks/use-launch-config";
import { LaunchConfigFields } from "./launch-config-fields";
import { api } from "@/api/client";
import { toast } from "sonner";
import { ExternalLink } from "lucide-react";
import type { RegistryImage, ServiceTemplate } from "@/lib/types";

interface LaunchModalProps {
  open: boolean;
  onClose: () => void;
  registryImage?: RegistryImage | null;
  template?: ServiceTemplate | null;
}

export function LaunchModal({ open, onClose, registryImage, template }: LaunchModalProps) {
  const createTemplate = useCreateTemplate();
  const updateTemplate = useUpdateTemplate();
  const createInstance = useCreateInstance();
  const { data: gpuInfo } = useGpuInfo();
  const cfg = useLaunchConfig({ registryImage, template });

  async function upsertTemplate() {
    const templateData = cfg.buildTemplateData();
    try {
      return await createTemplate.mutateAsync(templateData);
    } catch {
      const templates = await api.listTemplates();
      const existing = templates.find((t) => t.name === templateData.name);
      if (!existing) throw new Error("Failed to create or find template");
      return await updateTemplate.mutateAsync({ id: existing.id, data: templateData });
    }
  }

  async function handleSaveAndLaunch() {
    if (!cfg.name.trim() || !cfg.image.trim()) { toast.error("Name and image required"); return; }
    try {
      const tmpl = await upsertTemplate();
      await createInstance.mutateAsync({ template_id: tmpl.id, name: cfg.name, subdomain: cfg.subdomain });
      toast.success(`Instance "${cfg.name}" launched!`);
      onClose();
    } catch (e) {
      toast.error(`Launch failed: ${(e as Error).message}`);
    }
  }

  async function handleSaveTemplate() {
    if (!cfg.name.trim() || !cfg.image.trim()) { toast.error("Name and image required"); return; }
    try {
      await upsertTemplate();
      toast.success(`Template "${cfg.name}" saved!`);
      onClose();
    } catch (e) {
      toast.error(`Save failed: ${(e as Error).message}`);
    }
  }

  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="max-h-[90vh] w-[90vw] max-w-4xl overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-3">
            {cfg.icon && <img src={cfg.icon} alt="" className="h-8 w-8 rounded object-contain" />}
            {registryImage ? `Import: ${registryImage.name}` : template ? `Launch: ${template.display_name}` : "Custom Template"}
          </DialogTitle>
          {registryImage?.description && (
            <p className="text-xs text-muted-foreground line-clamp-2">{registryImage.description}</p>
          )}
        </DialogHeader>

        <LaunchConfigFields cfg={cfg} gpuInfo={gpuInfo} />

        {/* Changelog preview */}
        {registryImage?.changelog && registryImage.changelog.length > 0 && (
          <>
            <Separator />
            <details className="text-xs">
              <summary className="cursor-pointer text-muted-foreground hover:text-foreground">Changelog ({registryImage.changelog.length} entries)</summary>
              <div className="mt-2 space-y-1 max-h-24 overflow-y-auto">
                {registryImage.changelog.map((entry, i) => (
                  <div key={i} className="flex gap-2">
                    <span className="text-muted-foreground shrink-0">{entry.date}</span>
                    <span>{entry.desc}</span>
                  </div>
                ))}
              </div>
            </details>
          </>
        )}

        {/* Setup link */}
        {registryImage?.config?.application_setup && (
          <a href={registryImage.config.application_setup} target="_blank" rel="noreferrer" className="flex items-center gap-1 text-xs text-primary hover:underline">
            <ExternalLink className="h-3 w-3" /> Application Setup Guide
          </a>
        )}

        <Separator />
        <div className="flex gap-2">
          <Button onClick={handleSaveAndLaunch} className="flex-1" disabled={createTemplate.isPending || createInstance.isPending}>
            {createInstance.isPending ? "Launching..." : "Save & Launch"}
          </Button>
          <Button variant="secondary" onClick={handleSaveTemplate} disabled={createTemplate.isPending}>
            Save as Template
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
