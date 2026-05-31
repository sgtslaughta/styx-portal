import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { SELKIES_DEFAULTS, SELKIES_GROUPS } from "@/lib/selkies-defaults";
import { Switch } from "@/components/ui/switch";

interface SelkiesSettingsProps {
  envVars: Record<string, string>;
  onChange: (v: Record<string, string>) => void;
}

export function SelkiesSettings({ envVars, onChange }: SelkiesSettingsProps) {
  const [activeGroup, setActiveGroup] = useState<string>("Core");

  function toggleVar(name: string, defaultValue: string) {
    const next = { ...envVars };
    if (name in next) {
      delete next[name];
    } else {
      next[name] = defaultValue;
    }
    onChange(next);
  }

  function updateVar(name: string, value: string) {
    onChange({ ...envVars, [name]: value });
  }

  const groupVars = SELKIES_DEFAULTS.filter(v => v.group === activeGroup);

  return (
    <div className="space-y-3">
      <p className="text-[10px] text-muted-foreground">Toggle Selkies/LinuxServer options. Enabled vars merge into Environment tab.</p>
      <div className="flex gap-1 flex-wrap">
        {SELKIES_GROUPS.map(g => (
          <Button key={g} variant={activeGroup === g ? "default" : "ghost"} size="sm" className="text-[10px] h-6 px-2" onClick={() => setActiveGroup(g)}>
            {g}
          </Button>
        ))}
      </div>
      <div className="space-y-1.5 max-h-52 overflow-y-auto">
        {groupVars.map(v => {
          const isActive = v.name in envVars;
          return (
            <div key={v.name} className={`flex items-center gap-2 rounded-md border p-2 ${isActive ? "border-primary/30 bg-primary/5" : "border-border"}`}>
              <Switch checked={isActive} onCheckedChange={() => toggleVar(v.name, v.value)} className="scale-75" />
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <code className="text-[10px] font-semibold">{v.name}</code>
                  {v.type === "bool" && <Badge variant="outline" className="text-[8px] px-1 py-0">bool</Badge>}
                </div>
                <p className="text-[9px] text-muted-foreground truncate">{v.desc}</p>
              </div>
              {isActive && (
                v.type === "select" && v.options ? (
                  <select value={envVars[v.name] ?? v.value} onChange={(e) => updateVar(v.name, e.target.value)} className="h-6 rounded border border-border bg-background px-1 text-[10px]">
                    {v.options.map(o => <option key={o} value={o}>{o || "(none)"}</option>)}
                  </select>
                ) : v.type === "bool" ? (
                  <select value={envVars[v.name] ?? v.value} onChange={(e) => updateVar(v.name, e.target.value)} className="h-6 w-16 rounded border border-border bg-background px-1 text-[10px]">
                    <option value="true">true</option>
                    <option value="false">false</option>
                  </select>
                ) : (
                  <Input value={envVars[v.name] ?? v.value} onChange={(e) => updateVar(v.name, e.target.value)} className="h-6 w-28 text-[10px] font-mono" />
                )
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
