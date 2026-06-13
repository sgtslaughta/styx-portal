import { Input } from "@/components/ui/input";
import { LockedField } from "../controls/locked-field";
import { RepeatableRows } from "../controls/repeatable-rows";
import type { LaunchConfig } from "@/hooks/use-launch-config";

interface Props {
  cfg: LaunchConfig;
  isAdmin: boolean;
}

export function RawDockerSection({ cfg, isAdmin }: Props) {
  return (
    <div className="space-y-6 p-4">
      <LockedField locked={!isAdmin} label="Entrypoint">
        <Input
          placeholder="Separate multiple values with spaces"
          value={(cfg.entrypoint || []).join(" ")}
          disabled={!isAdmin}
          onChange={(e) => {
            const trimmed = e.target.value.trim();
            cfg.setEntrypoint(
              trimmed ? trimmed.split(/\s+/) : null
            );
          }}
        />
      </LockedField>

      <LockedField locked={!isAdmin} label="Command">
        <Input
          placeholder="Separate multiple values with spaces"
          value={(cfg.command || []).join(" ")}
          disabled={!isAdmin}
          onChange={(e) => {
            const trimmed = e.target.value.trim();
            cfg.setCommand(
              trimmed ? trimmed.split(/\s+/) : null
            );
          }}
        />
      </LockedField>

      <LockedField locked={!isAdmin} label="Extra Docker Args">
        <div className="space-y-2">
          <RepeatableRows
            rows={Object.entries(cfg.extraDockerArgs).map(([k, v]) => ({
              k,
              v: String(v),
            }))}
            blank={{ k: "", v: "" }}
            disabled={!isAdmin}
            onChange={(rows) =>
              cfg.setExtraDockerArgs(
                Object.fromEntries(
                  rows
                    .filter((r) => r.k && r.v)
                    .map((r) => [r.k, r.v])
                )
              )
            }
            addLabel="Add Argument"
            render={(row, update) => (
              <div className="flex gap-2">
                <Input
                  placeholder="Key"
                  value={row.k}
                  disabled={!isAdmin}
                  onChange={(e) => update({ ...row, k: e.target.value })}
                />
                <Input
                  placeholder="Value"
                  value={row.v}
                  disabled={!isAdmin}
                  onChange={(e) => update({ ...row, v: e.target.value })}
                />
              </div>
            )}
          />
        </div>
      </LockedField>
    </div>
  );
}
