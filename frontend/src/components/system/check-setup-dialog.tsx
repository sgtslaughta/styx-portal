import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { TurnSetupCheck } from "./turn-setup-check";
import { TurnSetupGuide } from "./turn-setup-guide";

export function CheckSetupDialog({ open, onOpenChange, provider }: { open: boolean; onOpenChange: (o: boolean) => void; provider: string }) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader><DialogTitle>Check setup</DialogTitle></DialogHeader>
        <TurnSetupCheck provider={provider} />
        <TurnSetupGuide provider={provider} />
      </DialogContent>
    </Dialog>
  );
}
