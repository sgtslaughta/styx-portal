import { useState } from "react";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";

/** Stages a new secret in the page batch; the token itself is never displayed back. */
export function ReplaceTokenDialog({ open, onOpenChange, onStage }: { open: boolean; onOpenChange: (o: boolean) => void; onStage: (v: string) => void }) {
  const [v, setV] = useState("");
  const done = () => { onStage(v.trim()); setV(""); onOpenChange(false); };
  return (
    <Dialog open={open} onOpenChange={(o) => { if (!o) setV(""); onOpenChange(o); }}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Replace API token</DialogTitle>
          <DialogDescription>Paste the new token. It is stored encrypted when you save changes and is never shown again.</DialogDescription>
        </DialogHeader>
        <input type="password" aria-label="New API token" autoComplete="new-password" value={v} onChange={(e) => setV(e.target.value)}
          className="h-9 w-full rounded-md border border-border bg-background px-3" />
        <DialogFooter>
          <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button type="button" disabled={!v.trim()} onClick={done}>Use this token</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
