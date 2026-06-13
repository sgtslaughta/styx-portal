import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { EnvEditor } from "../../env-editor";
import { Separator } from "@/components/ui/separator";
import type { LaunchConfig } from "@/hooks/use-launch-config";

interface Props {
  cfg: LaunchConfig;
  isAdmin: boolean;
}

export function EnvironmentSection({ cfg }: Props) {
  const updateEnv = (key: string, value: string) => {
    cfg.setEnvVars({ ...cfg.envVars, [key]: value });
  };

  return (
    <div className="space-y-6 p-4">
      <div>
        <Label className="text-xs uppercase tracking-wide text-muted-foreground mb-2 block">
          Environment Variables
        </Label>
        <EnvEditor
          value={cfg.envVars}
          onChange={cfg.setEnvVars}
          descriptions={cfg.envDescriptions}
        />
      </div>

      <Separator />

      <div className="space-y-3">
        <Label className="text-xs uppercase tracking-wide text-muted-foreground">
          LinuxServer.io Helpers
        </Label>
        <p className="text-xs text-muted-foreground">
          Common environment variables used by LinuxServer.io images
        </p>
        <div className="space-y-2">
          <div>
            <Label className="text-xs">PUID</Label>
            <Input
              placeholder="1000"
              value={cfg.envVars["PUID"] || ""}
              onChange={(e) => updateEnv("PUID", e.target.value)}
            />
          </div>
          <div>
            <Label className="text-xs">PGID</Label>
            <Input
              placeholder="1000"
              value={cfg.envVars["PGID"] || ""}
              onChange={(e) => updateEnv("PGID", e.target.value)}
            />
          </div>
          <div>
            <Label className="text-xs">TZ</Label>
            <Input
              placeholder="America/New_York"
              value={cfg.envVars["TZ"] || ""}
              onChange={(e) => updateEnv("TZ", e.target.value)}
            />
          </div>
        </div>
      </div>
    </div>
  );
}
