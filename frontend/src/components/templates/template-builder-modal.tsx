import { useEffect, useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { TemplateBuilder } from "./builder/template-builder";
import { useCreateTemplate, useUpdateTemplate } from "@/hooks/use-templates";
import { useLaunchConfig } from "@/hooks/use-launch-config";
import { useAuth } from "@/hooks/use-auth";
import { toast } from "sonner";
import type { ServiceTemplate } from "@/lib/types";

interface TemplateBuilderModalProps {
  open: boolean;
  mode: "new" | "edit" | "clone";
  template?: ServiceTemplate | null;
  onClose: () => void;
}

export function TemplateBuilderModal({
  open,
  mode,
  template,
  onClose,
}: TemplateBuilderModalProps) {
  const [saving, setSaving] = useState(false);
  const create = useCreateTemplate();
  const update = useUpdateTemplate();
  const { user } = useAuth();

  // Determine the source template for the config
  const sourceTemplate = mode === "new" ? null : template;
  const cfg = useLaunchConfig({ template: sourceTemplate });

  // For clone mode, clear the name
  useEffect(() => {
    if (mode === "clone") {
      cfg.setName("");
    }
  }, [mode, cfg]);

  const isAdmin = user?.role === "admin";

  const title =
    mode === "edit"
      ? "Edit template"
      : mode === "clone"
        ? "Clone template"
        : "New template";

  async function save(share: boolean) {
    if (!cfg.name.trim()) {
      toast.error("Template name is required");
      return;
    }
    if (!cfg.image.trim()) {
      toast.error("Image is required");
      return;
    }

    setSaving(true);
    try {
      const data = { ...cfg.buildTemplateData(), shared: share };
      if (mode === "edit" && template?.id) {
        await update.mutateAsync({ id: template.id, data });
        toast.success(share ? "Template saved & shared" : "Template saved");
      } else {
        await create.mutateAsync(data);
        toast.success(
          share ? "Template created & shared" : "Template created"
        );
      }
      onClose();
    } catch (e) {
      toast.error(`Save failed: ${(e as Error).message}`);
    } finally {
      setSaving(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="max-h-[90vh] w-[90vw] max-w-4xl overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
        </DialogHeader>

        <TemplateBuilder cfg={cfg} isAdmin={isAdmin} />

        <div className="flex gap-2 pt-4">
          <Button onClick={() => save(false)} disabled={saving}>
            Save
          </Button>
          <Button
            variant="secondary"
            onClick={() => save(true)}
            disabled={saving}
          >
            Save & Share
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
