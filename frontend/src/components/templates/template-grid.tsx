import { useNavigate } from "react-router";
import { Button } from "@/components/ui/button";
import { Plus, Copy } from "lucide-react";
import { useTemplates } from "@/hooks/use-templates";
import { TemplateCard } from "./template-card";
import type { ServiceTemplate } from "@/lib/types";

interface TemplateGridProps {
  onLaunch: (template: ServiceTemplate) => void;
  onImportRegistry?: () => void;
}

export function TemplateGrid({ onLaunch, onImportRegistry }: TemplateGridProps) {
  const navigate = useNavigate();
  const { data: templates, isLoading } = useTemplates();

  if (isLoading) {
    return (
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
        {[1, 2, 3].map((i) => <div key={i} className="styx-card h-40 animate-pulse rounded-xl" />)}
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex gap-2">
        <Button onClick={() => navigate("/templates/new")} size="sm">
          <Plus className="mr-1.5 h-3.5 w-3.5" />
          New Template
        </Button>
        {onImportRegistry && (
          <Button onClick={onImportRegistry} variant="secondary" size="sm">
            From Registry
          </Button>
        )}
      </div>

      {!templates?.length ? (
        <p className="py-8 text-center text-sm text-muted-foreground">No saved templates. Create one or import from the LinuxServer Registry.</p>
      ) : (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
          {templates.map((t) => (
            <TemplateCard
              key={t.id}
              template={t}
              onLaunch={onLaunch}
              onEdit={() => navigate(`/templates/${t.id}/edit`)}
              onClone={() => navigate(`/templates/new?clone=${t.id}`)}
            />
          ))}
        </div>
      )}
    </div>
  );
}
