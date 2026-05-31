import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Switch } from "@/components/ui/switch";
import { Gpu } from "lucide-react";

interface GpuIndicatorProps {
  gpuInfo: { available: boolean; type: string | null; devices: string[] } | undefined;
  gpuEnabled: boolean;
  setGpuEnabled: (v: boolean) => void;
  gpuDevices: string[];
  setGpuDevices: (v: string[]) => void;
}

export function GpuIndicator({ gpuInfo, gpuEnabled, setGpuEnabled, gpuDevices, setGpuDevices }: GpuIndicatorProps) {
  const [showDevices, setShowDevices] = useState(false);
  const allDevices = gpuInfo?.devices ?? [];

  function toggleDevice(dev: string) {
    setGpuDevices(gpuDevices.includes(dev) ? gpuDevices.filter(d => d !== dev) : [...gpuDevices, dev]);
  }

  return (
    <div className="rounded-lg border border-border p-3 space-y-2">
      <div className="flex items-center gap-4">
        <Gpu className="h-5 w-5 text-muted-foreground" />
        <div className="flex-1">
          <div className="flex items-center gap-2">
            <span className="text-sm font-medium">GPU Passthrough</span>
            {gpuInfo?.available ? (
              <Badge variant="outline" className="text-[10px] text-success border-success/30">
                {gpuInfo.type?.toUpperCase()} detected
              </Badge>
            ) : (
              <Badge variant="outline" className="text-[10px] text-warning border-warning/30">
                No GPU detected
              </Badge>
            )}
          </div>
          {gpuEnabled && gpuDevices.length === 0 && (
            <p className="text-[10px] text-muted-foreground mt-0.5">AUTO mode — all devices passed through</p>
          )}
          {gpuEnabled && gpuDevices.length > 0 && (
            <p className="text-[10px] text-muted-foreground mt-0.5">Manual: {gpuDevices.join(", ")}</p>
          )}
        </div>
        <Switch checked={gpuEnabled} onCheckedChange={setGpuEnabled} />
      </div>
      {gpuEnabled && allDevices.length > 0 && (
        <>
          <button onClick={() => setShowDevices(!showDevices)} className="text-[10px] text-primary hover:underline">
            {showDevices ? "▾ Hide device selection" : "▸ Override specific devices (default: auto)"}
          </button>
          {showDevices && (
            <div className="space-y-1 pl-9">
              {allDevices.map(dev => (
                <label key={dev} className="flex items-center gap-2 text-xs cursor-pointer">
                  <input type="checkbox" checked={gpuDevices.includes(dev)} onChange={() => toggleDevice(dev)} className="rounded" />
                  <code className="text-[10px]">{dev}</code>
                </label>
              ))}
              {gpuDevices.length > 0 && (
                <button onClick={() => setGpuDevices([])} className="text-[10px] text-muted-foreground hover:text-foreground">Reset to AUTO</button>
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
}
