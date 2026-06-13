import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";

export function ActiveSessionDialog({
  open, busy, onCancel, onEndAndSignOut,
}: {
  open: boolean;
  busy?: boolean;
  onCancel: () => void;
  onEndAndSignOut: () => void;
}) {
  return (
    <Dialog open={open} onOpenChange={(o) => { if (!o) onCancel(); }}>
      <DialogContent className="max-w-sm">
        <DialogHeader>
          <DialogTitle>You have an active session</DialogTitle>
        </DialogHeader>
        <p className="text-sm text-muted-foreground">
          A workstation desktop is still streaming. Signing out will end that
          session and disconnect the stream.
        </p>
        <DialogFooter>
          <Button variant="ghost" onClick={onCancel} disabled={busy}>Cancel</Button>
          <Button variant="destructive" onClick={onEndAndSignOut} disabled={busy}>
            {busy ? "Ending…" : "End session & sign out"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
