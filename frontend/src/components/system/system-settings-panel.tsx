import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { api, type Setting, type SettingGroup, type SettingValue } from "@/api/client";
import { SettingField, isChanged } from "@/components/settings/setting-field";
import { SavePill } from "@/components/settings/save-pill";
import { useUnsaved } from "@/components/settings/unsaved-context";

export function SystemSettingsPanel({ groups: only }: { groups?: string[] } = {}) {
  const qc = useQueryClient();
  const { data: all = [], isLoading } = useQuery({
    queryKey: ["system-settings"],
    queryFn: api.getSystemSettings,
  });
  const groups = only ? all.filter((g) => only.includes(g.group)) : all;

  // Only edits live here; untouched rows read the server value.
  const [edits, setEdits] = useState<Record<string, SettingValue>>({});
  const [errors, setErrors] = useState<Record<string, string>>({});
  const { setCount } = useUnsaved();

  const validate = (setting: Setting, value: SettingValue): string | null => {
    if (setting.type === "int") {
      if (value === "" || value === null) return "Required";
      const num = Number(value);
      if (isNaN(num)) return "Must be a number";
      if (setting.min !== null && num < setting.min) return `Minimum: ${setting.min}`;
      if (setting.max !== null && num > setting.max) return `Maximum: ${setting.max}`;
    } else if (setting.type === "rate") {
      if (!/^\d+\/\d+$/.test(String(value))) return "Format: number/number (e.g., 60/1000)";
    }
    return null;
  };

  const all_ = groups.flatMap((g) => g.settings);
  const dirtyKeys = all_.filter((s) => isChanged(s, edits[s.key])).map((s) => s.key);
  const dirty = dirtyKeys.length;

  useEffect(() => setCount(dirty), [dirty, setCount]);
  useEffect(() => () => setCount(0), [setCount]);

  const updateMutation = useMutation({
    mutationFn: (changes: Record<string, number | boolean | string>) =>
      api.updateSystemSettings(changes),
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: ["system-settings"] });
      setEdits({});
      setErrors({});
      toast.success("Settings updated");
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const drop = (key: string) => {
    setEdits((p) => { const n = { ...p }; delete n[key]; return n; });
    setErrors((p) => { const n = { ...p }; delete n[key]; return n; });
  };

  const handleChange = (key: string, value: SettingValue, setting: Setting) => {
    const v = setting.type === "int" && value !== "" ? Number(value) : value;
    setEdits((p) => ({ ...p, [key]: v }));
    const err = validate(setting, v);
    setErrors((p) => {
      const n = { ...p };
      if (err) n[key] = err; else delete n[key];
      return n;
    });
  };

  const handleSave = () => {
    const changes: Record<string, number | boolean | string> = {};
    let bad = false;
    all_.forEach((s) => {
      if (!isChanged(s, edits[s.key])) return;
      if (validate(s, edits[s.key] ?? null)) bad = true;
      else changes[s.key] = (edits[s.key] ?? "") as number | boolean | string;
    });
    if (bad) return void toast.error("Please fix validation errors before saving");
    if (Object.keys(changes).length > 0) updateMutation.mutate(changes);
  };

  if (isLoading) {
    return <div className="text-sm text-muted-foreground">Loading settings...</div>;
  }

  const busy = updateMutation.isPending;

  return (
    <>
      <div data-testid="settings-grid" className="groups">
        {groups.map((group: SettingGroup) => (
          <fieldset key={group.group} className="grp">
            <legend>{group.label}</legend>
            {group.settings.map((setting: Setting) => (
              <SettingField
                key={setting.key}
                setting={setting}
                value={edits[setting.key]}
                error={errors[setting.key]}
                disabled={busy}
                onChange={(v) => handleChange(setting.key, v, setting)}
                onRestore={() => drop(setting.key)}
                onClear={() => setEdits((p) => ({ ...p, [setting.key]: null }))}
                // Staged like any edit: nothing is sent until Save changes.
                onResetDefault={() => handleChange(setting.key, setting.default, setting)}
              />
            ))}
          </fieldset>
        ))}
      </div>
      <SavePill
        count={dirty}
        saving={updateMutation.isPending}
        onSave={handleSave}
        onDiscard={() => { setEdits({}); setErrors({}); }}
      />
    </>
  );
}
