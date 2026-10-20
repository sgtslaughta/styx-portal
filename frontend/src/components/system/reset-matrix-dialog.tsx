import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { KeyRound } from "lucide-react";
import { api } from "@/api/client";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";

/** Confirm, then remove a user's sign-in card (they sign in with password only until they enroll again). */
export function ResetMatrixDialog({ user, onClose }: {
  user: { id: string; username: string } | null;
  onClose: () => void;
}) {
  const qc = useQueryClient();
  const reset = useMutation({
    mutationFn: (id: string) => api.adminResetMatrix(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["users"] });
      toast.success("Sign-in card reset");
      onClose();
    },
    onError: (e: Error) => toast.error(e.message),
  });

  return (
    <Dialog open={!!user} onOpenChange={(open) => !open && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <KeyRound className="h-5 w-5" />
            Reset sign-in card?
          </DialogTitle>
          <DialogDescription>
            {user && (
              <>
                <strong>{user.username}</strong>'s card stops working at once. They sign in with
                their password only until they set up a new card.
              </>
            )}
          </DialogDescription>
        </DialogHeader>
        <div className="flex gap-2 justify-end">
          <Button variant="outline" onClick={onClose} disabled={reset.isPending}>Cancel</Button>
          <Button variant="destructive" onClick={() => user && reset.mutate(user.id)}
                  disabled={reset.isPending}>
            Reset card
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
