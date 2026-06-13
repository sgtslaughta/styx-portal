import { SliderInput } from "../controls/slider-input";
import { EnumSelect } from "../controls/enum-select";
import { ToggleField } from "../controls/toggle-field";
import type { LaunchConfig } from "@/hooks/use-launch-config";

interface Props {
  cfg: LaunchConfig;
  isAdmin: boolean;
}

function gb(s: string): number {
  return Number(String(s).replace(/g$/i, "")) || 0;
}

export function ResourcesSection({ cfg }: Props) {
  return (
    <div className="space-y-6 p-4">
      <SliderInput
        label="Memory Limit"
        min={0.5}
        max={32}
        step={0.5}
        value={gb(cfg.memoryLimit)}
        unit="GB"
        tooltip="Container memory limit"
        onChange={(v) => cfg.setMemoryLimit(`${v}g`)}
      />

      <SliderInput
        label="CPU Limit"
        min={0.25}
        max={8}
        step={0.25}
        value={Number(cfg.cpuLimit)}
        unit="cores"
        tooltip="Container CPU limit"
        onChange={(v) => cfg.setCpuLimit(String(v))}
      />

      <SliderInput
        label="Shared Memory"
        min={0.5}
        max={16}
        step={0.5}
        value={gb(cfg.shmSize)}
        unit="GB"
        tooltip="Shared memory size for IPC"
        onChange={(v) => cfg.setShmSize(`${v}g`)}
      />

      <EnumSelect
        label="Restart Policy"
        value={cfg.restartPolicy}
        options={["no", "on-failure", "unless-stopped", "always"]}
        tooltip="Container restart behavior"
        onChange={cfg.setRestartPolicy}
      />

      <ToggleField
        label="GPU Passthrough"
        checked={cfg.gpuEnabled}
        tooltip="Enable GPU access for the container"
        onChange={cfg.setGpuEnabled}
      />
    </div>
  );
}
