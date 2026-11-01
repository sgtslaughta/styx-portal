import { useState } from "react";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/common/confirm-dialog";

type Props = { count: number; onUnlock: () => void; onDelete: () => void; onClear: () => void };

/** "N selected · Unlock · Delete"; Delete asks first. */
export function UsersBulkBar({ count, onUnlock, onDelete, onClear }: Props) {
  const [ask, setAsk] = useState(false);
  if (!count) return null;
  return (
    <div className="toolbar" role="region" aria-label="Bulk actions">
      <span className="text-sm">{count} selected</span>
      <Button size="sm" variant="secondary" onClick={onUnlock}>Unlock</Button>
      <Button size="sm" variant="destructive" onClick={() => setAsk(true)}>Delete</Button>
      <Button size="sm" variant="ghost" onClick={onClear}>Clear</Button>
      <ConfirmDialog open={ask} onOpenChange={setAsk} variant="destructive" confirmLabel="Delete"
        title={`Delete ${count} ${count === 1 ? "user" : "users"} permanently?`}
        description="This cannot be undone. You are skipped, and users who own instances or templates fail with an error."
        onConfirm={() => { setAsk(false); onDelete(); }} />
    </div>
  );
}
