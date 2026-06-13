import { useState } from "react";
import { useParams, useNavigate, useSearchParams } from "react-router";
import { Button } from "@/components/ui/button";
import { TemplateBuilder } from "@/components/templates/builder/template-builder";
import { useTemplates, useCreateTemplate, useUpdateTemplate } from "@/hooks/use-templates";
import { useLaunchConfig } from "@/hooks/use-launch-config";
import { useAuth } from "@/hooks/use-auth";
import { toast } from "sonner";
import type { ServiceTemplate } from "@/lib/types";

interface TemplateBuilderPageProps {
  mode: "new" | "edit";
}

export function TemplateBuilderPage({ mode }: TemplateBuilderPageProps) {
  const { id } = useParams<{ id?: string }>();
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const { data: templates } = useTemplates();
  const create = useCreateTemplate();
  const update = useUpdateTemplate();
  const { user } = useAuth();
  const [saving, setSaving] = useState(false);

  // Find the template to edit, or the template to clone from
  let existing: ServiceTemplate | null = null;
  const cloneId = searchParams.get("clone");
  if (mode === "edit" && id) {
    existing = templates?.find((t) => t.id === id) ?? null;
  } else if (cloneId) {
    existing = templates?.find((t) => t.id === cloneId) ?? null;
  }

  const cfg = useLaunchConfig({ template: existing });

  // For clone mode, clear the name to make it new
  if (cloneId) {
    cfg.setName("");
  }

  const isAdmin = user?.role === "admin";

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
      if (mode === "edit" && id) {
        await update.mutateAsync({ id, data });
        toast.success(share ? "Template saved & shared" : "Template saved");
      } else {
        await create.mutateAsync(data);
        toast.success(share ? "Template created & shared" : "Template created");
      }
      navigate("/");
    } catch (e) {
      toast.error(`Save failed: ${(e as Error).message}`);
    } finally {
      setSaving(false);
    }
  }

  const title =
    mode === "edit" ? "Edit template" : cloneId ? "Clone template" : "New template";

  return (
    <div className="mx-auto max-w-4xl space-y-4 p-6">
      <h1 className="text-lg font-semibold">{title}</h1>
      <TemplateBuilder cfg={cfg} isAdmin={isAdmin} />
      <div className="flex gap-2 pt-4">
        <Button
          onClick={() => save(false)}
          disabled={saving}
        >
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
    </div>
  );
}
