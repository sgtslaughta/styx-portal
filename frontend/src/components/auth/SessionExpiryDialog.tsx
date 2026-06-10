import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";

export function SessionExpiryDialog({
  open, onStay, onSignOut,
}: { open: boolean; onStay: () => void; onSignOut: () => void }) {
  return (
    <Dialog open={open}>
      <DialogContent className="max-w-sm" onInteractOutside={(e) => e.preventDefault()}>
        <DialogHeader>
          <DialogTitle>Your session is about to expire</DialogTitle>
        </DialogHeader>
        <p className="text-sm text-muted-foreground">
          You'll be signed out soon for security. Stay signed in to keep working.
        </p>
        <DialogFooter>
          <Button variant="ghost" onClick={onSignOut}>Sign out</Button>
          <Button onClick={onStay}>Stay signed in</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
