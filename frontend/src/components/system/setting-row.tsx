import { HelpCircle, RotateCcw } from "lucide-react";
import type { Setting, SettingValue } from "@/api/client";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";

type Props = {
  setting: Setting;
  value: SettingValue | undefined;
  error?: string;
  disabled: boolean;
  onChange: (value: SettingValue) => void;
  onReset: () => void;
  onClear: () => void;
};

function Control({ setting, value, error, disabled, onChange }: Props) {
  const { type } = setting;
  if (type === "bool") {
    return (
      <div className="flex items-center gap-2">
        <Switch checked={Boolean(value)} onCheckedChange={onChange} disabled={disabled} />
        <span className="text-sm text-muted-foreground">{value ? "Enabled" : "Disabled"}</span>
      </div>
    );
  }
  if (type === "enum") {
    return (
      <select
        aria-label={setting.label}
        className="rounded border border-border bg-surface px-2 py-1.5 text-sm"
        value={String(value ?? "")}
        disabled={disabled}
        onChange={(e) => onChange(e.target.value)}
      >
        {(setting.choices ?? []).map((c) => (
          <option key={c} value={c}>
            {c}
          </option>
        ))}
      </select>
    );
  }
  if (type === "secret") {
    return (
      <div className="flex items-center gap-2">
        <Badge variant={setting.is_set ? "default" : "outline"}>
          {setting.is_set ? "Set" : "Not set"}
        </Badge>
        <Input
          type="password"
          aria-label={setting.label}
          autoComplete="new-password"
          value={String(value ?? "")}
          onChange={(e) => onChange(e.target.value)}
          disabled={disabled}
          placeholder={setting.is_set ? "Enter a new value to replace" : "Enter value"}
        />
      </div>
    );
  }
  return (
    <div>
      <Input
        type={type === "int" ? "number" : "text"}
        aria-label={setting.label}
        value={String(value ?? "")}
        onChange={(e) => onChange(e.target.value)}
        disabled={disabled}
        className={error ? "border-destructive" : ""}
        placeholder={String(setting.default ?? "")}
        min={type === "int" && setting.min !== null ? setting.min : undefined}
        max={type === "int" && setting.max !== null ? setting.max : undefined}
      />
      {error && <p className="mt-1 text-xs text-destructive">{error}</p>}
    </div>
  );
}

export function SettingRow(props: Props) {
  const { setting, value, disabled, onReset, onClear } = props;
  const isSecret = setting.type === "secret";
  return (
    <div className="flex items-start gap-4 rounded-lg border border-border/50 p-4 hover:bg-muted/20 transition-colors">
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 mb-1">
          <label className="text-sm font-medium leading-none">{setting.label}</label>
          <TooltipProvider>
            <Tooltip>
              <TooltipTrigger asChild>
                <HelpCircle className="h-4 w-4 text-muted-foreground hover:text-foreground transition-colors cursor-help" />
              </TooltipTrigger>
              <TooltipContent side="right" className="max-w-xs">
                {setting.help}
              </TooltipContent>
            </Tooltip>
          </TooltipProvider>
        </div>
        {setting.help && <p className="text-xs text-muted-foreground mb-3">{setting.help}</p>}
        <Control {...props} />
      </div>
      <div className="flex flex-col items-end gap-2">
        {isSecret ? (
          setting.is_set && (
            <Button variant="outline" size="sm" onClick={onClear} disabled={disabled}>
              Clear
            </Button>
          )
        ) : (
          value !== setting.default && (
            <Button
              variant="ghost"
              size="sm"
              onClick={onReset}
              disabled={disabled}
              className="text-muted-foreground hover:text-foreground"
              title="Reset to default"
            >
              <RotateCcw className="h-4 w-4" />
            </Button>
          )
        )}
        {!isSecret && (
          <span className="text-xs text-muted-foreground text-right">
            Default: <code className="font-mono">{String(setting.default)}</code>
          </span>
        )}
      </div>
    </div>
  );
}
