import * as React from "react";

import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

interface ConfirmDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description?: React.ReactNode;
  confirmLabel?: string;
  cancelLabel?: string;
  variant?: "default" | "destructive";
  /** When set, the user must type this exact string to enable the confirm button. */
  confirmPhrase?: string;
  onConfirm: () => void;
}

export function ConfirmDialog({
  open, onOpenChange, title, description,
  confirmLabel = "Confirm", cancelLabel = "Cancel",
  variant = "default", confirmPhrase, onConfirm,
}: ConfirmDialogProps) {
  const [typed, setTyped] = React.useState("");

  React.useEffect(() => {
    if (!open) setTyped("");
  }, [open]);

  const locked = confirmPhrase != null && typed !== confirmPhrase;

  function handleConfirm() {
    if (locked) return;
    onConfirm();
    onOpenChange(false);
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          {description && <DialogDescription>{description}</DialogDescription>}
        </DialogHeader>

        {confirmPhrase != null && (
          <div className="space-y-1.5">
            <Label htmlFor="confirm-phrase" className="text-xs text-muted-foreground">
              Type <span className="font-mono font-semibold text-foreground">{confirmPhrase}</span> to confirm
            </Label>
            <Input
              id="confirm-phrase"
              value={typed}
              autoFocus
              autoComplete="off"
              onChange={(e) => setTyped(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter") handleConfirm(); }}
            />
          </div>
        )}

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>{cancelLabel}</Button>
          <Button variant={variant} disabled={locked} onClick={handleConfirm}>{confirmLabel}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
