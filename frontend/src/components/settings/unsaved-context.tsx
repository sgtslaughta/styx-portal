import { createContext, useCallback, useContext, useMemo, useRef, useState, type ReactNode } from "react";
import { ConfirmDialog } from "@/components/common/confirm-dialog";

type Unsaved = {
  count: number;
  setCount: (n: number) => void;
  /** True (and runs proceed) when nothing is unsaved; else opens the discard dialog and returns false. */
  confirmLeave: (proceed?: () => void) => boolean;
};

const Ctx = createContext<Unsaved>({ count: 0, setCount: () => {}, confirmLeave: (p) => { p?.(); return true; } });
export const useUnsaved = () => useContext(Ctx);

export function UnsavedProvider({ children }: { children: ReactNode }) {
  const [count, setCount] = useState(0);
  const [open, setOpen] = useState(false);
  const pending = useRef<(() => void) | undefined>(undefined);

  const confirmLeave = useCallback((proceed?: () => void) => {
    if (count === 0) { proceed?.(); return true; }
    pending.current = proceed;
    setOpen(true);
    return false;
  }, [count]);

  const value = useMemo(() => ({ count, setCount, confirmLeave }), [count, confirmLeave]);
  return (
    <Ctx.Provider value={value}>
      {children}
      <ConfirmDialog
        open={open}
        onOpenChange={setOpen}
        title={`Discard ${count} unsaved ${count === 1 ? "change" : "changes"}?`}
        description="Leaving this section drops edits you have not saved."
        confirmLabel="Discard"
        variant="destructive"
        onConfirm={() => { setCount(0); pending.current?.(); pending.current = undefined; }}
      />
    </Ctx.Provider>
  );
}
