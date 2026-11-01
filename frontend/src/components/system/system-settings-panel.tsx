import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useSearchParams } from "react-router";
import { toast } from "sonner";
import { api, type Setting, type SettingGroup, type SettingValue } from "@/api/client";
import { SlidersHorizontal } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { SettingsGroupNav } from "./settings-group-nav";
import { SettingRow } from "./setting-row";
import { TurnCostCard } from "./turn-cost-card";
import { TurnSetupCheck } from "./turn-setup-check";
import { TurnSetupGuide } from "./turn-setup-guide";
import { isSettingVisible } from "./webrtc-fields";

export function SystemSettingsPanel() {
  const qc = useQueryClient();
  const { data: groups = [], isLoading } = useQuery({
    queryKey: ["system-settings"],
    queryFn: api.getSystemSettings,
  });

  const [localState, setLocalState] = useState<Record<string, SettingValue>>({});
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [params, setParams] = useSearchParams();

  // Initialize local state when data loads
  if (groups.length > 0 && Object.keys(localState).length === 0) {
    const initial: Record<string, SettingValue> = {};
    groups.forEach((g) => {
      g.settings.forEach((s) => {
        if (s.type !== "secret") initial[s.key] = s.value;
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
    mutationFn: (changes: Record<string, number | boolean | string>) =>
      api.updateSystemSettings(changes),
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: ["system-settings"] });
      setLocalState((prev) => {
        const next = { ...prev };
        groups.forEach((g) => g.settings.forEach((s) => s.type === "secret" && delete next[s.key]));
        return next;
      });
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

  const providerRow = (g: SettingGroup) =>
    g.settings.find((s) => s.key === "WEBRTC_TURN_PROVIDER")?.value;

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
    const changes: Record<string, number | boolean | string> = {};
    let hasErrors = false;

    group.settings.forEach((s) => {
      const currentValue = localState[s.key] ?? s.value;
      if (currentValue !== s.value) {
        const err = validate(s, currentValue);
        if (err) {
          hasErrors = true;
        } else {
          changes[s.key] = currentValue as number | boolean | string;
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

  const clearSecret = (key: string) => updateMutation.mutate({ [key]: "" });

  const handleReset = (key: string) => {
    resetMutation.mutate(key);
  };

  const isDirty = (g: SettingGroup) =>
    g.settings.some((s) => {
      const v = localState[s.key];
      if (s.type === "secret") return v !== undefined && v !== "";
      return (v !== undefined && v !== s.value) || s.key in errors;
    });

  if (isLoading) {
    return <div className="text-sm text-muted-foreground">Loading settings...</div>;
  }

  const wanted = params.get("group");
  const active = groups.find((g) => g.group === wanted) ?? groups[0];

  return (
    <div className="flex flex-col gap-4 md:flex-row md:gap-6">
      <SettingsGroupNav
        items={groups.map((g) => ({ id: g.group, label: g.label, dirty: isDirty(g) }))}
        activeId={active?.group ?? ""}
        onSelect={(id) => setParams((p) => { p.set("group", id); return p; })}
      />
      <div className="min-w-0 flex-1 space-y-6">
      {(active ? [active] : []).map((group: SettingGroup) => (
        <div key={group.group} className="space-y-6">
        <Card className="styx-card">
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
            {group.group === "webrtc" && (
              <TurnSetupGuide provider={localState.WEBRTC_TURN_PROVIDER ?? providerRow(group)} />
            )}
            <div className="space-y-4">
              {group.settings
                .filter((s) =>
                  group.group !== "webrtc" ||
                  isSettingVisible(s.key, localState.WEBRTC_TURN_PROVIDER ?? providerRow(group))
                )
                .map((setting: Setting) => (
                  <SettingRow
                    key={setting.key}
                    setting={setting}
                    value={localState[setting.key]}
                    error={errors[setting.key]}
                    disabled={updateMutation.isPending || resetMutation.isPending}
                    onChange={(v) => handleChange(setting.key, v, setting)}
                    onClear={() => clearSecret(setting.key)}
                    onReset={() => {
                      setLocalState((prev) => ({ ...prev, [setting.key]: setting.default }));
                      setErrors((prev) => {
                        const next = { ...prev };
                        delete next[setting.key];
                        return next;
                      });
                      handleReset(setting.key);
                    }}
                  />
                ))}
            </div>
          </CardContent>
        </Card>
        {group.group === "webrtc" && <TurnSetupCheck provider={String(providerRow(group) ?? "none")} />}
        {group.group === "webrtc" && <TurnCostCard />}
        </div>
      ))}
      </div>
    </div>
  );
}
