import { Trash2, Play } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { useDeleteTemplate } from "@/hooks/use-templates";
import { toast } from "sonner";
import type { ServiceTemplate } from "@/lib/types";

interface TemplateCardProps {
  template: ServiceTemplate;
  onLaunch: (template: ServiceTemplate) => void;
}

export function TemplateCard({ template, onLaunch }: TemplateCardProps) {
  const deleteTemplate = useDeleteTemplate();

  function handleDelete(e: React.MouseEvent) {
    e.stopPropagation();
    if (!confirm(`Delete template "${template.display_name}"?`)) return;
    deleteTemplate.mutate(template.id, {
      onError: (err) => toast.error(`Delete failed: ${err.message}`),
    });
  }

  return (
    <div className="overflow-hidden rounded-xl border border-border bg-card p-4 transition-colors hover:border-primary/50">
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
        {template.category && <Badge variant="secondary" className="text-[10px]">{template.category}</Badge>}
        {template.gpu_enabled && <Badge variant="secondary" className="text-[10px]">GPU</Badge>}
        {template.memory_limit && <Badge variant="outline" className="text-[10px]">{template.memory_limit} RAM</Badge>}
      </div>
      <div className="flex gap-2">
        <Button size="sm" className="flex-1" onClick={() => onLaunch(template)}>
          <Play className="mr-1.5 h-3 w-3" /> Launch
        </Button>
        <Button size="sm" variant="ghost" onClick={handleDelete}>
          <Trash2 className="h-3 w-3" />
        </Button>
      </div>
    </div>
  );
}
