import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { EnumSelect } from "../controls/enum-select";
import { RepeatableRows } from "../controls/repeatable-rows";
import { ToggleField } from "../controls/toggle-field";
import type { LaunchConfig, ExtraPortEntry } from "@/hooks/use-launch-config";

interface Props {
  cfg: LaunchConfig;
  isAdmin: boolean;
}

export function PortsNetworkSection({ cfg }: Props) {
  return (
    <div className="space-y-6 p-4">
      <div className="space-y-2">
        <Label className="text-xs uppercase tracking-wide text-muted-foreground">
          Primary Port
        </Label>
        <div className="flex gap-2">
          <Input
            type="number"
            placeholder="3001"
            value={cfg.internalPort}
            onChange={(e) => cfg.setInternalPort(Number(e.target.value))}
            className="flex-1"
          />
          <EnumSelect
            label="Protocol"
            value={cfg.internalProtocol}
            options={["https", "http"]}
            onChange={cfg.setInternalProtocol}
          />
        </div>
      </div>

      <div className="space-y-2">
        <Label className="text-xs uppercase tracking-wide text-muted-foreground">
          Extra Ports
        </Label>
        <p className="text-xs text-muted-foreground">
          Path-prefixed apps must support a base-URL / subpath setting, or
          absolute asset URLs will break.
        </p>
        <RepeatableRows<ExtraPortEntry>
          rows={cfg.extraPorts}
          blank={{
            container_port: 0,
            label: "",
            slug: "",
            strip_prefix: false,
          }}
          onChange={cfg.setExtraPorts}
          addLabel="Add Port"
          render={(row, update) => (
            <div className="space-y-1">
              <Input
                type="number"
                placeholder="Container port"
                value={row.container_port}
                onChange={(e) =>
                  update({
                    ...row,
                    container_port: Number(e.target.value),
                  })
                }
              />
              <Input
                placeholder="Label (e.g., API)"
                value={row.label}
                onChange={(e) => update({ ...row, label: e.target.value })}
              />
              <Input
                placeholder="Slug (e.g., api)"
                value={row.slug}
                onChange={(e) => update({ ...row, slug: e.target.value })}
              />
              <ToggleField
                label="Strip Prefix"
                checked={row.strip_prefix}
                onChange={(v) => update({ ...row, strip_prefix: v })}
              />
            </div>
          )}
        />
      </div>

      <div className="space-y-2">
        <Label className="text-xs uppercase tracking-wide text-muted-foreground">
          Extra Hosts
        </Label>
        <RepeatableRows
          rows={Object.entries(cfg.extraHosts).map(([host, ip]) => ({
            host,
            ip,
          }))}
          blank={{ host: "", ip: "" }}
          onChange={(rows) =>
            cfg.setExtraHosts(
              Object.fromEntries(
                rows
                  .filter((r) => r.host && r.ip)
                  .map((r) => [r.host, r.ip])
              )
            )
          }
          addLabel="Add Host"
          render={(row, update) => (
            <div className="flex gap-2">
              <Input
                placeholder="Hostname"
                value={row.host}
                onChange={(e) => update({ ...row, host: e.target.value })}
              />
              <Input
                placeholder="IP address"
                value={row.ip}
                onChange={(e) => update({ ...row, ip: e.target.value })}
              />
            </div>
          )}
        />
      </div>
    </div>
  );
}
