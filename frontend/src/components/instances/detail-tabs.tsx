import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import type { Instance } from "@/lib/types";

interface GeneralTabProps {
  instance: Instance;
  name: string;
  setName: (name: string) => void;
  markDirty: () => void;
}

export function GeneralTab({ instance, name, setName, markDirty }: GeneralTabProps) {
  return (
    <div className="space-y-3">
      <div>
        <Label>Instance Name</Label>
        <Input
          value={name}
          onChange={(e) => {
            setName(e.target.value);
            markDirty();
          }}
        />
      </div>
      <div className="grid grid-cols-2 gap-3 text-xs text-muted-foreground">
        <div>
          <span>Template ID</span>
          <div className="mt-0.5 font-mono">{instance.template_id.slice(0, 8)}...</div>
        </div>
        <div>
          <span>Instance ID</span>
          <div className="mt-0.5 font-mono">{instance.id.slice(0, 8)}...</div>
        </div>
      </div>
      {instance.volume_names.length > 0 && (
        <div>
          <Label className="text-xs text-muted-foreground">Volumes (persistent)</Label>
          <div className="mt-1 space-y-1">
            {instance.volume_names.map((v) => (
              <div key={v} className="rounded bg-secondary px-2 py-1 font-mono text-xs">
                {v}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

interface SessionTabProps {
  idleTimeout: string;
  setIdleTimeout: (v: string) => void;
  gracePeriod: string;
  setGracePeriod: (v: string) => void;
  timeoutAction: string;
  setTimeoutAction: (v: string) => void;
  neverTimeout: boolean;
  setNeverTimeout: (v: boolean) => void;
  markDirty: () => void;
}

export function SessionTab({
  idleTimeout, setIdleTimeout,
  gracePeriod, setGracePeriod,
  timeoutAction, setTimeoutAction,
  neverTimeout, setNeverTimeout,
  markDirty,
}: SessionTabProps) {
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 gap-3">
        <div>
          <Label>Idle Timeout</Label>
          <Input
            value={idleTimeout}
            onChange={(e) => {
              setIdleTimeout(e.target.value);
              markDirty();
            }}
          />
        </div>
        <div>
          <Label>Grace Period</Label>
          <Input
            value={gracePeriod}
            onChange={(e) => {
              setGracePeriod(e.target.value);
              markDirty();
            }}
          />
        </div>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div>
          <Label>Timeout Action</Label>
          <select
            value={timeoutAction}
            onChange={(e) => {
              setTimeoutAction(e.target.value);
              markDirty();
            }}
            className="mt-1 h-9 w-full rounded-md border border-input bg-background px-3 text-sm"
          >
            <option value="stop">Stop</option>
            <option value="destroy">Destroy</option>
          </select>
        </div>
        <div className="flex items-end gap-3 pb-1">
          <Switch
            checked={neverTimeout}
            onCheckedChange={(v) => {
              setNeverTimeout(v);
              markDirty();
            }}
          />
          <Label className="text-sm">Never Timeout</Label>
        </div>
      </div>
    </div>
  );
}
