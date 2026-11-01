import { useState } from "react";
import { AlertTriangle, Check, Copy, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";

export function TempPasswordDialog({ password, onClose }: { password: string | null; onClose: () => void }) {
  const [copied, setCopied] = useState(false);
  const copy = () => {
    if (!password) return;
    void navigator.clipboard.writeText(password);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };
  return (
    <Dialog open={!!password} onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Temporary password</DialogTitle>
          <DialogDescription>
            Share this one-time password with the user. They must change it on their next sign-in.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-4">
          <div className="flex items-center gap-2">
            <code className="flex-1 select-all break-all rounded bg-muted px-3 py-2 font-mono text-sm">{password}</code>
            <Button size="sm" variant="secondary" onClick={copy} disabled={copied} title="Copy to clipboard">
              {copied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
            </Button>
          </div>
          <p className="text-xs text-muted-foreground">Store this securely. You cannot retrieve it again.</p>
          <Button onClick={onClose} className="w-full">Done</Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

type DeleteProps = { username: string | null; pending: boolean; onCancel: () => void; onConfirm: () => void };
export function DeleteUserDialog({ username, pending, onCancel, onConfirm }: DeleteProps) {
  return (
    <Dialog open={username !== null} onOpenChange={(o) => !o && onCancel()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-destructive">
            <AlertTriangle className="h-5 w-5" />Delete user permanently?
          </DialogTitle>
          <DialogDescription>
            This will permanently delete <strong>{username}</strong>. This action cannot be undone.
          </DialogDescription>
        </DialogHeader>
        <p className="rounded-md border border-destructive/20 bg-destructive/5 p-3 text-xs font-medium text-destructive">
          The user must not own any instances or templates. If they do, assign or delete them first.
        </p>
        <div className="flex justify-end gap-2">
          <Button variant="outline" onClick={onCancel} disabled={pending}>Cancel</Button>
          <Button variant="destructive" onClick={onConfirm} disabled={pending}>
            <Trash2 className="mr-2 h-4 w-4" />{pending ? "Deleting…" : "Delete"}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
