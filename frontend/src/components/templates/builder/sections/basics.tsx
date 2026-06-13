import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { FieldTooltip } from "../controls/field-tooltip";
import type { LaunchConfig } from "@/hooks/use-launch-config";

interface Props {
  cfg: LaunchConfig;
  isAdmin: boolean;
}

export function BasicsSection({ cfg }: Props) {
  return (
    <div className="space-y-4 p-4">
      <div className="space-y-1.5">
        <Label className="text-xs uppercase tracking-wide text-muted-foreground">
          Name
          <FieldTooltip text="Display name for this service" />
        </Label>
        <Input
          value={cfg.name}
          onChange={(e) => cfg.setName(e.target.value)}
          placeholder="e.g., Code Server"
        />
      </div>

      <div className="space-y-1.5">
        <Label className="text-xs uppercase tracking-wide text-muted-foreground">
          Image
          <FieldTooltip text="Docker image URI (e.g., lscr.io/linuxserver/code-server:latest)" />
        </Label>
        <Input
          value={cfg.image}
          onChange={(e) => cfg.setImage(e.target.value)}
          placeholder="e.g., lscr.io/linuxserver/code-server:latest"
        />
      </div>

      <div className="space-y-1.5">
        <Label className="text-xs uppercase tracking-wide text-muted-foreground">
          Icon URL
          <FieldTooltip text="Logo or icon URL for the service" />
        </Label>
        <Input
          value={cfg.icon}
          onChange={(e) => cfg.setIcon(e.target.value)}
          placeholder="https://..."
        />
      </div>
    </div>
  );
}
