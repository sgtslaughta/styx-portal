import { useState } from "react";
import { Trash2, Play, Copy, Pencil } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { ConfirmDialog } from "@/components/common/confirm-dialog";
import { useDeleteTemplate } from "@/hooks/use-templates";
import { useAuth } from "@/hooks/use-auth";
import { toast } from "sonner";
import type { ServiceTemplate } from "@/lib/types";

interface TemplateCardProps {
  template: ServiceTemplate;
  onLaunch: (template: ServiceTemplate) => void;
  onClone?: () => void;
  onEdit?: () => void;
}

export function TemplateCard({ template, onLaunch, onClone, onEdit }: TemplateCardProps) {
  const [confirmOpen, setConfirmOpen] = useState(false);
  const deleteTemplate = useDeleteTemplate();
  const { user } = useAuth();

  const isOwner = user && template.owner_id === user.id;
  const isAdmin = user?.role === "admin";
  const canEdit = isOwner || isAdmin;

  function handleDelete(e: React.MouseEvent) {
    e.stopPropagation();
    setConfirmOpen(true);
  }

  function doDelete() {
    deleteTemplate.mutate(template.id, {
      onError: (err) => toast.error(`Delete failed: ${err.message}`),
      onSuccess: () => toast.success(`Deleted ${template.display_name}`),
    });
  }

  return (
    <div className="styx-card overflow-hidden rounded-xl p-4 transition-colors hover:border-primary/50">
      <div className="mb-3 flex items-start gap-3">
        {template.icon?.startsWith("http") ? (
          <img src={template.icon} alt="" className="h-8 w-8 rounded object-contain" />
        ) : (
          <span className="text-2xl">{template.icon ?? "📦"}</span>
        )}
        <div className="flex-1">
          <h3 className="font-semibold">{template.display_name}</h3>
          <p className="mt-0.5 text-xs text-muted-foreground line-clamp-2">{template.description}</p>
        </div>
      </div>
      <div className="mb-3 flex flex-wrap gap-1">
        {template.shared && !isOwner && <Badge variant="secondary" className="text-[10px]">Shared</Badge>}
        {template.category && <Badge variant="secondary" className="text-[10px]">{template.category}</Badge>}
        {template.gpu_enabled && <Badge variant="secondary" className="text-[10px]">GPU</Badge>}
        {template.dind && <Badge variant="secondary" className="text-[10px]">DinD</Badge>}
        {template.memory_limit && <Badge variant="outline" className="text-[10px]">{template.memory_limit} RAM</Badge>}
      </div>
      <div className="flex gap-2">
        <Button size="sm" className="flex-1" onClick={() => onLaunch(template)}>
          <Play className="mr-1.5 h-3 w-3" /> Launch
        </Button>
        {canEdit && (
          <>
            {onEdit && (
              <Button size="sm" variant="ghost" onClick={onEdit} title="Edit template">
                <Pencil className="h-3 w-3" />
              </Button>
            )}
            {onClone && (
              <Button size="sm" variant="ghost" onClick={onClone} title="Clone template">
                <Copy className="h-3 w-3" />
              </Button>
            )}
            <Button size="sm" variant="ghost" onClick={handleDelete} title="Delete template">
              <Trash2 className="h-3 w-3" />
            </Button>
          </>
        )}
      </div>
      <ConfirmDialog
        open={confirmOpen}
        onOpenChange={setConfirmOpen}
        title={`Delete template "${template.display_name}"?`}
        description="This removes the template definition. Running instances are unaffected."
        confirmLabel="Delete"
        variant="destructive"
        confirmPhrase={template.display_name}
        onConfirm={doDelete}
      />
    </div>
  );
}
