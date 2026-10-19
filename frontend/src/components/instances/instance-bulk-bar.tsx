import { useState } from "react";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { Pause, Play, Square, Trash2, X } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/common/confirm-dialog";
import {
  useDeleteInstance, usePauseInstance, useStartInstance, useStopInstance, useUnpauseInstance,
} from "@/hooks/use-instances";
import { shortError } from "@/lib/utils";
import type { Instance } from "@/lib/types";

type IdMutation = { mutate: (id: string, opts: { onError: (e: Error) => void }) => void };

/** Floating bar acting on the multi-selected instances. */
export function InstanceBulkBar({ selected, onClear }: { selected: Instance[]; onClear: () => void }) {
  const reduce = useReducedMotion();
  const [confirm, setConfirm] = useState(false);
  const start = useStartInstance();
  const stop = useStopInstance();
  const pause = usePauseInstance();
  const unpause = useUnpauseInstance();
  const destroy = useDeleteInstance();
  const busy = start.isPending || stop.isPending || pause.isPending || unpause.isPending || destroy.isPending;
  const running = selected.filter((i) => i.status === "running" || i.status === "idle");
  const stopped = selected.filter((i) => i.status === "stopped" || i.status === "error");
  const paused = selected.filter((i) => i.status === "paused");
  const fail = (i: Instance) => (e: Error) => { console.error(i.name, e); toast.error(shortError(`${i.name}: ${e.message}`)); };

  function bulk(list: Instance[], mut: IdMutation, verb: string) {
    list.forEach((i) => mut.mutate(i.id, { onError: fail(i) }));
    toast.success(`${verb} ${list.length} instance(s)`);
    onClear();
  }
  function destroyAll() {
    selected.forEach((i) => destroy.mutate({ id: i.id, removeVolumes: false }, { onError: fail(i) }));
    toast.success(`Destroying ${selected.length} instance(s)`);
    onClear();
  }

  return (
    <>
      <AnimatePresence>
        {selected.length > 0 && (
          <motion.div
            initial={reduce ? undefined : { y: 60, opacity: 0 }}
            animate={reduce ? undefined : { y: 0, opacity: 1 }}
            exit={reduce ? undefined : { y: 60, opacity: 0 }}
            transition={{ type: "spring", stiffness: 400, damping: 30 }}
            className="fixed bottom-4 left-1/2 z-50 flex -translate-x-1/2 items-center gap-2 rounded-xl border border-border bg-card px-4 py-2.5 shadow-2xl"
          >
            <span className="mr-1 text-xs font-medium text-foreground">{selected.length} selected</span>
            {stopped.length > 0 && (
              <Button size="sm" variant="secondary" disabled={busy} onClick={() => bulk(stopped, start, "Starting")}>
                <Play /> Start {stopped.length}
              </Button>
            )}
            {running.length > 0 && (
              <Button size="sm" variant="secondary" disabled={busy} onClick={() => bulk(running, pause, "Pausing")}>
                <Pause /> Pause {running.length}
              </Button>
            )}
            {paused.length > 0 && (
              <Button size="sm" variant="secondary" disabled={busy} onClick={() => bulk(paused, unpause, "Resuming")}>
                <Play /> Resume {paused.length}
              </Button>
            )}
            {running.length + paused.length > 0 && (
              <Button size="sm" variant="secondary" disabled={busy} onClick={() => bulk([...running, ...paused], stop, "Stopping")}>
                <Square /> Stop {running.length + paused.length}
              </Button>
            )}
            <Button size="sm" variant="ghost" className="text-destructive hover:text-destructive" disabled={busy} onClick={() => setConfirm(true)}>
              <Trash2 /> Destroy
            </Button>
            <div className="mx-1 h-5 w-px bg-border" />
            <Button size="icon-sm" variant="ghost" onClick={onClear} title="Clear selection" aria-label="Clear selection">
              <X />
            </Button>
          </motion.div>
        )}
      </AnimatePresence>
      <ConfirmDialog
        open={confirm}
        onOpenChange={setConfirm}
        title={`Destroy ${selected.length} instance(s)?`}
        description="Containers will be removed. Named volumes are kept."
        confirmLabel="Destroy"
        variant="destructive"
        confirmPhrase="destroy"
        onConfirm={destroyAll}
      />
    </>
  );
}
