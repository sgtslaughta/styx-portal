import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { toast } from "sonner";
import { api } from "@/api/client";
import { SlidersHorizontal, HelpCircle, RotateCcw } from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";

type SettingValue = number | boolean | string;

type Setting = {
  key: string;
  label: string;
  help: string;
  type: "int" | "bool" | "rate";
  value: SettingValue;
  default: SettingValue;
  min: number | null;
  max: number | null;
};

type SettingGroup = {
  group: string;
  label: string;
  settings: Setting[];
};

export function SystemSettingsPanel() {
  const qc = useQueryClient();
  const { data: groups = [], isLoading } = useQuery({
    queryKey: ["system-settings"],
    queryFn: api.getSystemSettings,
  });

  const [localState, setLocalState] = useState<Record<string, SettingValue>>({});
  const [errors, setErrors] = useState<Record<string, string>>({});

  // Initialize local state when data loads
  if (groups.length > 0 && Object.keys(localState).length === 0) {
    const initial: Record<string, SettingValue> = {};
    groups.forEach((g) => {
      g.settings.forEach((s) => {
        initial[s.key] = s.value;
      });
    });
    setLocalState(initial);
  }

  const validate = (setting: Setting, value: SettingValue): string | null => {
    if (setting.type === "int") {
      const num = Number(value);
      if (isNaN(num)) return "Must be a number";
      if (setting.min !== null && num < setting.min) return `Minimum: ${setting.min}`;
      if (setting.max !== null && num > setting.max) return `Maximum: ${setting.max}`;
    } else if (setting.type === "rate") {
      if (!/^\d+\/\d+$/.test(String(value))) return "Format: number/number (e.g., 60/1000)";
    }
    return null;
  };

  const updateMutation = useMutation({
    mutationFn: (changes: Record<string, SettingValue>) =>
      api.updateSystemSettings(changes),
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: ["system-settings"] });
      toast.success("Settings updated");
      setErrors({});
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const resetMutation = useMutation({
    mutationFn: (key: string) => api.resetSystemSetting(key),
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: ["system-settings"] });
      toast.success("Setting reset to default");
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const handleChange = (key: string, value: SettingValue, setting: Setting) => {
    const newValue = setting.type === "int" ? (value === "" ? "" : Number(value)) : value;
    setLocalState((prev) => ({ ...prev, [key]: newValue }));

    const err = validate(setting, newValue);
    if (err) {
      setErrors((prev) => ({ ...prev, [key]: err }));
    } else {
      setErrors((prev) => {
        const next = { ...prev };
        delete next[key];
        return next;
      });
    }
  };

  const handleSaveGroup = (group: SettingGroup) => {
    const changes: Record<string, SettingValue> = {};
    let hasErrors = false;

    group.settings.forEach((s) => {
      if (localState[s.key] !== s.value) {
        const err = validate(s, localState[s.key]);
        if (err) {
          hasErrors = true;
        } else {
          changes[s.key] = localState[s.key];
        }
      }
    });

    if (hasErrors) {
      toast.error("Please fix validation errors before saving");
      return;
    }

    if (Object.keys(changes).length > 0) {
      updateMutation.mutate(changes);
    }
  };

  const handleReset = (key: string) => {
    resetMutation.mutate(key);
  };

  if (isLoading) {
    return <div className="text-sm text-muted-foreground">Loading settings...</div>;
  }

  return (
    <div className="space-y-6">
      {groups.map((group: SettingGroup) => (
        <Card key={group.group} className="styx-card">
          <CardHeader className="pb-4">
            <div className="flex items-center justify-between gap-3">
              <div className="flex items-center gap-3">
                <div className="rounded-lg bg-primary/10 p-2">
                  <SlidersHorizontal className="h-5 w-5 text-primary" />
                </div>
                <div>
                  <CardTitle>{group.label}</CardTitle>
                </div>
              </div>
              <Button
                onClick={() => handleSaveGroup(group)}
                disabled={
                  updateMutation.isPending ||
                  Object.keys(errors).some((k) => group.settings.some((s) => s.key === k))
                }
                size="sm"
              >
                {updateMutation.isPending ? "Saving..." : "Save"}
              </Button>
            </div>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-4">
              {group.settings.map((setting: Setting) => (
                <div
                  key={setting.key}
                  className="flex items-start gap-4 rounded-lg border border-border/50 p-4 hover:bg-muted/20 transition-colors"
                >
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      <label className="text-sm font-medium leading-none">
                        {setting.label}
                      </label>
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
                    {setting.help && (
                      <p className="text-xs text-muted-foreground mb-3">{setting.help}</p>
                    )}

                    {setting.type === "bool" ? (
                      <div className="flex items-center gap-2">
                        <Switch
                          checked={Boolean(localState[setting.key])}
                          onCheckedChange={(checked) =>
                            handleChange(setting.key, checked, setting)
                          }
                          disabled={updateMutation.isPending}
                        />
                        <span className="text-sm text-muted-foreground">
                          {localState[setting.key] ? "Enabled" : "Disabled"}
                        </span>
                      </div>
                    ) : (
                      <div>
                        <Input
                          type={setting.type === "int" ? "number" : "text"}
                          value={localState[setting.key]}
                          onChange={(e) =>
                            handleChange(setting.key, e.target.value, setting)
                          }
                          disabled={updateMutation.isPending}
                          className={
                            errors[setting.key] ? "border-destructive" : ""
                          }
                          placeholder={String(setting.default)}
                          min={
                            setting.type === "int" && setting.min !== null
                              ? setting.min
                              : undefined
                          }
                          max={
                            setting.type === "int" && setting.max !== null
                              ? setting.max
                              : undefined
                          }
                        />
                        {errors[setting.key] && (
                          <p className="mt-1 text-xs text-destructive">
                            {errors[setting.key]}
                          </p>
                        )}
                      </div>
                    )}
                  </div>

                  <div className="flex flex-col items-end gap-2">
                    {localState[setting.key] !== setting.default && (
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => {
                          setLocalState((prev) => ({
                            ...prev,
                            [setting.key]: setting.default,
                          }));
                          setErrors((prev) => {
                            const next = { ...prev };
                            delete next[setting.key];
                            return next;
                          });
                          handleReset(setting.key);
                        }}
                        disabled={resetMutation.isPending}
                        className="text-muted-foreground hover:text-foreground"
                        title="Reset to default"
                      >
                        <RotateCcw className="h-4 w-4" />
                      </Button>
                    )}
                    <span className="text-xs text-muted-foreground text-right">
                      Default:{" "}
                      <code className="font-mono">{String(setting.default)}</code>
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
