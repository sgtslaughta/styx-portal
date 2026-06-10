import { Plus, Trash2 } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";

interface EnvEditorProps {
  value: Record<string, string>;
  onChange: (value: Record<string, string>) => void;
  descriptions?: Record<string, string>;
}

export function EnvEditor({ value, onChange, descriptions }: EnvEditorProps) {
  const entries = Object.entries(value);

  function update(oldKey: string, newKey: string, newVal: string) {
    const next = { ...value };
    if (oldKey !== newKey) delete next[oldKey];
    next[newKey] = newVal;
    onChange(next);
  }

  function remove(key: string) {
    const next = { ...value };
    delete next[key];
    onChange(next);
  }

  function add() {
    onChange({ ...value, "": "" });
  }

  return (
    <div className="space-y-2">
      {entries.map(([key, val], i) => (
        <div key={i} className="flex items-start gap-2 min-w-0">
          <div className="flex-1 min-w-0">
            <Input value={key} onChange={(e) => update(key, e.target.value, val)} placeholder="KEY" className="font-mono text-xs" />
            {descriptions?.[key] && <p className="mt-0.5 text-[10px] text-muted-foreground truncate">{descriptions[key]}</p>}
          </div>
          <Input value={val} onChange={(e) => update(key, key, e.target.value)} placeholder="value" className="flex-1 min-w-0 font-mono text-xs" />
          <Button variant="ghost" size="icon" className="h-9 w-9" onClick={() => remove(key)} aria-label="Delete variable">
            <Trash2 className="h-3 w-3" />
          </Button>
        </div>
      ))}
      <Button variant="outline" size="sm" onClick={add}>
        <Plus className="mr-1.5 h-3 w-3" /> Add Variable
      </Button>
    </div>
  );
}
