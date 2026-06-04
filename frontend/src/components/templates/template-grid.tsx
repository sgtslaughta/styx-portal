import { useTemplates } from "@/hooks/use-templates";
import { TemplateCard } from "./template-card";
import type { ServiceTemplate } from "@/lib/types";

interface TemplateGridProps {
  onLaunch: (template: ServiceTemplate) => void;
}

export function TemplateGrid({ onLaunch }: TemplateGridProps) {
  const { data: templates, isLoading } = useTemplates();

  if (isLoading) {
    return (
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
        {[1, 2, 3].map((i) => <div key={i} className="styx-card h-40 animate-pulse rounded-xl" />)}
      </div>
    );
  }

  if (!templates?.length) {
    return <p className="py-8 text-center text-sm text-muted-foreground">No saved templates. Import one from the LinuxServer Registry.</p>;
  }

  return (
    <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
      {templates.map((t) => <TemplateCard key={t.id} template={t} onLaunch={onLaunch} />)}
    </div>
  );
}
