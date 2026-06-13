import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { LockedField } from "../controls/locked-field";
import { ToggleField } from "../controls/toggle-field";
import { RepeatableRows } from "../controls/repeatable-rows";
import type { LaunchConfig } from "@/hooks/use-launch-config";

interface Props {
  cfg: LaunchConfig;
  isAdmin: boolean;
}

export function SecuritySection({ cfg, isAdmin }: Props) {
  return (
    <div className="space-y-6 p-4">
      <LockedField locked={!isAdmin} label="Privileged Mode">
        <ToggleField
          label="Allow privileged container"
          checked={cfg.privileged}
          tooltip="Container runs with full privileges"
          onChange={cfg.setPrivileged}
          disabled={!isAdmin}
        />
      </LockedField>

      <LockedField locked={!isAdmin} label="Device Access">
        <div className="space-y-2">
          <RepeatableRows
            rows={cfg.devices.map((d) => ({ v: d }))}
            blank={{ v: "" }}
            disabled={!isAdmin}
            onChange={(rows) =>
              cfg.setDevices(rows.map((r) => r.v).filter(Boolean))
            }
            addLabel="Add Device"
            render={(row, update) => (
              <Input
                placeholder="/dev/ttyUSB0:/dev/ttyUSB0"
                value={row.v}
                disabled={!isAdmin}
                onChange={(e) => update({ v: e.target.value })}
              />
            )}
          />
        </div>
      </LockedField>
    </div>
  );
}
