import { useCallback } from "react";
import { api } from "@/api/client";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { ProfilesList } from "@/components/system/profiles-list";

interface Props {
  userId: string;
  username: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function UserProfilesDialog({ userId, username, open, onOpenChange }: Props) {
  const load = useCallback(() => api.getUserProfiles(userId), [userId]);
  const remove = useCallback((t: string) => api.deleteUserProfile(userId, t), [userId]);
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Profiles for {username}</DialogTitle>
          <DialogDescription>Persistent profiles saved per template.</DialogDescription>
        </DialogHeader>
        {open && userId && <ProfilesList load={load} remove={remove} actionLabel="Delete" />}
      </DialogContent>
    </Dialog>
  );
}
