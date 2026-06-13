import { useState } from "react";
import { cn } from "@/lib/utils";
import { BasicsSection } from "./sections/basics";
import { ResourcesSection } from "./sections/resources";
import { StorageSection } from "./sections/storage";
import { PortsNetworkSection } from "./sections/ports-network";
import { EnvironmentSection } from "./sections/environment";
import { SecuritySection } from "./sections/security";
import { RawDockerSection } from "./sections/raw-docker";
import { Lock } from "lucide-react";
import type { LaunchConfig } from "@/hooks/use-launch-config";

const SECTIONS = [
  { id: "basics", label: "Basics", Comp: BasicsSection, risk: false },
  {
    id: "resources",
    label: "Resources",
    Comp: ResourcesSection,
    risk: false,
  },
  { id: "storage", label: "Storage", Comp: StorageSection, risk: false },
  {
    id: "ports",
    label: "Ports & Network",
    Comp: PortsNetworkSection,
    risk: false,
  },
  {
    id: "environment",
    label: "Environment",
    Comp: EnvironmentSection,
    risk: false,
  },
  {
    id: "security",
    label: "Security",
    Comp: SecuritySection,
    risk: true,
  },
  {
    id: "raw",
    label: "Raw Docker",
    Comp: RawDockerSection,
    risk: true,
  },
] as const;

export function TemplateBuilder({
  cfg,
  isAdmin,
}: {
  cfg: LaunchConfig;
  isAdmin: boolean;
}) {
  const [active, setActive] = useState("basics");
  const Active = SECTIONS.find((s) => s.id === active)!.Comp;

  return (
    <div className="flex gap-4 min-h-[300px]">
      <nav className="w-40 shrink-0 space-y-1">
        {SECTIONS.map((s) => (
          <button
            key={s.id}
            type="button"
            onClick={() => setActive(s.id)}
            className={cn(
              "flex w-full items-center gap-1.5 rounded-md px-3 py-2 text-left text-sm",
              active === s.id
                ? "bg-primary/15 text-foreground"
                : "text-muted-foreground hover:bg-muted"
            )}
          >
            {s.risk && <Lock className="h-3 w-3" />} {s.label}
          </button>
        ))}
      </nav>
      <div className="min-w-0 flex-1">
        <Active cfg={cfg} isAdmin={isAdmin} />
      </div>
    </div>
  );
}
