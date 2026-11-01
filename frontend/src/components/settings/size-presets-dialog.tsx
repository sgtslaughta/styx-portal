import { useState } from "react";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";

export type Preset = { id: string; label: string; cpus: number; memory_gb: number; gpu: boolean };
export const MAX_PRESETS = 6;

const slug = (s: string) => s.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") || "size";

function uniqueId(label: string, taken: Set<string>) {
  const base = slug(label);
  let id = base;
  for (let n = 2; taken.has(id); n++) id = `${base}-${n}`;
  return id;
}

function problem(rows: Preset[]): string | null {
  if (rows.length < 1 || rows.length > MAX_PRESETS) return `Keep between 1 and ${MAX_PRESETS} sizes`;
  if (rows.some((r) => !r.label.trim())) return "Every size needs a name";
  if (rows.some((r) => !(r.cpus >= 1 && r.cpus <= 64))) return "CPUs must be 1 to 64";
  if (rows.some((r) => !(r.memory_gb >= 1 && r.memory_gb <= 512))) return "Memory must be 1 to 512 GB";
  return null;
}

type Props = { open: boolean; presets: Preset[]; onOpenChange: (o: boolean) => void; onApply: (p: Preset[]) => void };

export function SizePresetsDialog({ open, presets, onOpenChange, onApply }: Props) {
  const [rows, setRows] = useState<Preset[]>(presets);
  const [seen, setSeen] = useState(open);
  if (open !== seen) { setSeen(open); if (open) setRows(presets); }  // re-seed each time it opens
  const err = problem(rows);
  const patch = (i: number, p: Partial<Preset>) => setRows((r) => r.map((x, j) => (j === i ? { ...x, ...p } : x)));
  const add = () => setRows((r) => [...r, { id: uniqueId("Custom", new Set(r.map((x) => x.id))), label: "Custom", cpus: 2, memory_gb: 4, gpu: false }]);
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Container sizes</DialogTitle>
          <DialogDescription>Sizes offered when someone launches a container. Applied when you save changes.</DialogDescription>
        </DialogHeader>
        <div className="preset-rows">
          {rows.map((r, i) => (
            <div className="preset-row" key={r.id}>
              <input type="text" aria-label={`Size ${i + 1} name`} value={r.label} onChange={(e) => patch(i, { label: e.target.value })} />
              <input type="number" aria-label={`Size ${i + 1} CPUs`} value={r.cpus} onChange={(e) => patch(i, { cpus: Number(e.target.value) })} />
              <input type="number" aria-label={`Size ${i + 1} memory GB`} value={r.memory_gb} onChange={(e) => patch(i, { memory_gb: Number(e.target.value) })} />
              <label><input type="checkbox" aria-label={`Size ${i + 1} GPU`} checked={r.gpu} onChange={(e) => patch(i, { gpu: e.target.checked })} /> GPU</label>
              <Button type="button" variant="ghost" size="sm" aria-label={`Remove size ${i + 1}`} disabled={rows.length <= 1}
                onClick={() => setRows((x) => x.filter((_, j) => j !== i))}>Remove</Button>
            </div>
          ))}
        </div>
        <small className="text-muted-foreground">Columns: name, CPUs, memory in GB, GPU</small>
        {err && <p role="alert" className="text-sm text-destructive">{err}</p>}
        <DialogFooter>
          <Button type="button" variant="outline" onClick={add} disabled={rows.length >= MAX_PRESETS}>Add a size</Button>
          <Button type="button" disabled={!!err} onClick={() => { onApply(rows); onOpenChange(false); }}>Done</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
