import type { MountChange } from "@/api/client";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";

const now = (c: MountChange) => (c.created ? "(no file yet)" : c.old || "(not set)");

export function MountConsentDialog({ open, appName, changes, backupHint, onConfirm, onCancel }: {
  open: boolean; appName: string; changes: MountChange[]; backupHint?: string; onConfirm: () => void; onCancel: () => void;
}) {
  return (
    <Dialog open={open} onOpenChange={(o) => { if (!o) onCancel(); }}>
      <DialogContent className="sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>{`Change ${appName}'s settings?`}</DialogTitle>
          <DialogDescription>Styx didn't create this container, so it asks first.</DialogDescription>
        </DialogHeader>
        <div className="overflow-x-auto">
          <table className="hidden w-full text-left text-sm sm:table">
            <thead>
              <tr className="text-muted-foreground">
                <th scope="col" className="py-1 pr-3 font-medium">File</th>
                <th scope="col" className="py-1 pr-3 font-medium">Setting</th>
                <th scope="col" className="py-1 pr-3 font-medium">Now</th>
                <th scope="col" className="py-1 font-medium">After</th>
              </tr>
            </thead>
            <tbody>
              {changes.map((c) => (
                <tr key={`${c.target}:${c.key}`} className="border-t border-border align-top font-mono text-xs">
                  <td className="py-1.5 pr-3 break-all">{c.target}{c.created ? " (new file)" : ""}</td>
                  <td className="py-1.5 pr-3 break-all">{c.key}</td>
                  <td className="py-1.5 pr-3">{now(c)}</td>
                  <td className="py-1.5">{c.new}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <dl className="space-y-3 sm:hidden">
            {changes.map((c) => (
              <div key={`${c.target}:${c.key}`} className="rounded-md border border-border p-3 font-mono text-xs">
                <dt className="break-all"><span className="text-muted-foreground">{c.target}{c.created ? " (new file)" : ""}</span> {c.key}</dt>
                <dd className="mt-1 break-all"><span className="text-muted-foreground">Now</span> {now(c)}</dd>
                <dd className="break-all"><span className="text-muted-foreground">After</span> {c.new}</dd>
              </div>
            ))}
          </dl>
        </div>
        {changes.some((c) => c.created) && (
          <p className="text-sm text-muted-foreground">
            {`Styx creates this file. Undoing leaves it with an empty base path, which is ${appName}'s default.`}
          </p>
        )}
        <p className="text-sm text-muted-foreground">
          Styx backs up the file first and restores it if {appName} doesn't come back.{backupHint ? ` ${backupHint}` : ""}
        </p>
        <p className="text-sm text-muted-foreground">{appName} restarts (about 30 seconds).</p>
        <DialogFooter>
          <Button variant="outline" onClick={onCancel}>Not now</Button>
          <Button onClick={onConfirm}>{`Restart ${appName} and apply`}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
