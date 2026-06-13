import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ToggleField } from "../controls/toggle-field";
import { RepeatableRows } from "../controls/repeatable-rows";
import type { LaunchConfig, VolumeEntry } from "@/hooks/use-launch-config";

interface Props {
  cfg: LaunchConfig;
  isAdmin: boolean;
}

export function StorageSection({ cfg }: Props) {
  return (
    <div className="space-y-6 p-4">
      <div className="space-y-2">
        <Label className="text-xs uppercase tracking-wide text-muted-foreground">
          Volumes
        </Label>
        <RepeatableRows<VolumeEntry>
          rows={cfg.volumes}
          blank={{ name: "", mount: "" }}
          onChange={cfg.setVolumes}
          addLabel="Add Volume"
          render={(row, update) => (
            <div className="space-y-1">
              <Input
                placeholder="Volume name"
                value={row.name}
                onChange={(e) => update({ ...row, name: e.target.value })}
              />
              <Input
                placeholder="Mount path (e.g., /data)"
                value={row.mount}
                onChange={(e) => update({ ...row, mount: e.target.value })}
              />
            </div>
          )}
        />
      </div>

      <ToggleField
        label="Read-Only Root Filesystem"
        checked={cfg.readOnlyRootfs}
        tooltip="Mount root filesystem as read-only"
        onChange={cfg.setReadOnlyRootfs}
      />

      <div className="space-y-2">
        <Label className="text-xs uppercase tracking-wide text-muted-foreground">
          Tmpfs Mounts
        </Label>
        <RepeatableRows
          rows={cfg.tmpfs.map((v) => ({ v }))}
          blank={{ v: "" }}
          onChange={(rows) =>
            cfg.setTmpfs(rows.map((r) => r.v).filter(Boolean))
          }
          addLabel="Add Tmpfs"
          render={(row, update) => (
            <Input
              placeholder="/tmp"
              value={row.v}
              onChange={(e) => update({ v: e.target.value })}
            />
          )}
        />
      </div>
    </div>
  );
}
