import { useState } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { slugify } from "@/lib/utils";
import { useCreateTemplate, useUpdateTemplate, useTemplates } from "@/hooks/use-templates";
import { useCreateInstance } from "@/hooks/use-instances";
import { useLaunchConfig } from "@/hooks/use-launch-config";
import { useAuth } from "@/hooks/use-auth";
import { useWaveTransition } from "@/components/effects/transition-provider";
import { LaunchOptions } from "./launch-options";
import { EasyLaunch } from "./easy-launch";
import { TemplateBuilder } from "./builder/template-builder";
import { api } from "@/api/client";
import { toast } from "sonner";
import { ExternalLink, ChevronLeft } from "lucide-react";
import type { RegistryImage, ServiceTemplate } from "@/lib/types";

interface LaunchModalProps {
  open: boolean;
  onClose: () => void;
  registryImage?: RegistryImage | null;
  template?: ServiceTemplate | null;
}

export function LaunchModal(props: LaunchModalProps) {
  const { registryImage, template } = props;
  const { data: templates, isLoading } = useTemplates();
  const existing = !template && registryImage ? templates?.find((t) => t.name === slugify(registryImage.name)) : undefined;
  if (registryImage && !template && isLoading) return null;
  return <LaunchModalBody key={existing?.id ?? "new"} {...props} existing={existing} />;
}

function LaunchModalBody({ open, onClose, registryImage: regProp, template: tmplProp, existing }: LaunchModalProps & { existing?: ServiceTemplate }) {
  // A registry import that matches a saved template launches from that template instead.
  const template = tmplProp ?? existing ?? null;
  const registryImage = existing ? null : regProp;
  const [mode, setMode] = useState<"easy" | "advanced">("easy");
  const [useProfile, setUseProfile] = useState(false);
  const [useGpu, setUseGpu] = useState(true);
  const createTemplate = useCreateTemplate();
  const updateTemplate = useUpdateTemplate();
  const createInstance = useCreateInstance();
  const { user } = useAuth();
  const wave = useWaveTransition();
  const cfg = useLaunchConfig({ registryImage, template });

  // Derive domain from window.location.hostname (e.g., "portal.example.com" → "example.com")
  // For localhost or single-label domains, fall back to empty string
  const domain = (() => {
    try {
      const hostname = window.location.hostname;
      if (hostname === "localhost" || hostname === "127.0.0.1" || hostname === "[::1]") return "";
      const parts = hostname.split(".");
      return parts.length > 2 ? parts.slice(1).join(".") : hostname;
    } catch {
      return "";
    }
  })();

  const isAdmin = user?.role === "admin";

  // Launching never overwrites a saved template; only the explicit "Save" does (merged, keeping admin fields).
  async function upsertTemplate(update: boolean) {
    if (template && !update) return template;
    const templateData = cfg.buildTemplateData();
    if (!template) {
      try {
        return await createTemplate.mutateAsync(templateData);
      } catch {
        const found = (await api.listTemplates()).find((t) => t.name === templateData.name);
        if (!found) throw new Error("Failed to create or find template");
        if (!update) return found;
        return await saveOver(found, templateData);
      }
    }
    return await saveOver(template, templateData);
  }

  function saveOver(existingTmpl: ServiceTemplate, data: ReturnType<typeof cfg.buildTemplateData>) {
    const merged = {
      ...data,
      profile_mount: data.profile_mount ?? existingTmpl.profile_mount ?? null,
      gpu_enabled: data.gpu_enabled || existingTmpl.gpu_enabled,
      gpu_count: data.gpu_count || existingTmpl.gpu_count,
    };
    return updateTemplate.mutateAsync({ id: existingTmpl.id, data: merged });
  }

  async function handleSaveAndLaunch() {
    if (!cfg.name.trim() || !cfg.image.trim()) { toast.error("Name and image required"); return; }
    try {
      const tmpl = await upsertTemplate(false);
      await createInstance.mutateAsync({ template_id: tmpl.id, name: cfg.name, subdomain: cfg.subdomain,
        use_profile: !!cfg.profileMount.trim() && useProfile,
        use_gpu: useGpu });
      onClose();
      wave.play(`Launching ${cfg.name}…`);
      toast.success(`Instance "${cfg.name}" launched!`);
    } catch (e) {
      toast.error(`Launch failed: ${(e as Error).message}`);
    }
  }

  async function handleSaveTemplate() {
    if (!cfg.name.trim() || !cfg.image.trim()) { toast.error("Name and image required"); return; }
    try {
      await upsertTemplate(true);
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
          <div className="flex items-start justify-between gap-4">
            <div className="flex items-center gap-3">
              {cfg.icon && <img src={cfg.icon} alt="" className="h-8 w-8 rounded object-contain" />}
              <div>
                <DialogTitle>
                  {regProp ? `Import: ${regProp.name}` : template ? `Launch: ${template.display_name}` : "Custom Template"}
                </DialogTitle>
                {registryImage?.description && (
                  <p className="text-xs text-muted-foreground line-clamp-2">{registryImage.description}</p>
                )}
              </div>
            </div>
            {mode === "advanced" && (
              <button
                type="button"
                className="text-xs text-muted-foreground hover:text-foreground transition-colors flex items-center gap-1 whitespace-nowrap"
                onClick={() => setMode("easy")}
              >
                <ChevronLeft className="h-3 w-3" /> Easy mode
              </button>
            )}
          </div>
        </DialogHeader>

        {existing && (
          <p className="text-xs text-muted-foreground">
            Using your existing template “{existing.display_name}” — edit it in Templates to change its settings.
          </p>
        )}

        {mode === "easy" ? (
          <EasyLaunch
            cfg={cfg}
            domain={domain}
            onLaunch={handleSaveAndLaunch}
            onAdvanced={() => setMode("advanced")}
            launching={createInstance.isPending}
          />
        ) : (
          <TemplateBuilder cfg={cfg} isAdmin={isAdmin} />
        )}

        <LaunchOptions
          showProfile={!!cfg.profileMount.trim()}
          showGpu={cfg.gpuEnabled && !!user?.can_use_gpu}
          useProfile={useProfile} onProfile={setUseProfile}
          useGpu={useGpu} onGpu={setUseGpu}
        />

        {mode === "advanced" && (
          <>
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
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}
