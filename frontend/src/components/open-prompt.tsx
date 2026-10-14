import { createContext, useCallback, useContext, useRef, useState, type ReactNode } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { api, type Me, type OpenMode } from "@/api/client";
import { Button } from "@/components/ui/button";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";

export type OpenGroup = "workspaces" | "apps";
type Run = (mode: OpenMode) => void;
type Choose = (group: OpenGroup, name: string, run: Run) => void;
const KEY = { workspaces: "open_workspaces", apps: "open_apps" } as const;
const SAVE_FAILED = "Couldn't save your choice";

export const useOpenPrefs = () => useQuery<Me>({ queryKey: ["me"], queryFn: api.me, staleTime: Infinity });

export function useSavePrefs() {
  const qc = useQueryClient();
  return useMutation({ mutationFn: api.setOpenPrefs, onSuccess: (me) => qc.setQueryData(["me"], me) });
}

const Ctx = createContext<Choose | null>(null);
const direct: Choose = (_g, _n, run) => run("new_tab");

/** `choose(group, name, run)`: runs per the saved preference, or asks once. `run` must open
 *  synchronously (window.open inside the click). Outside a provider it just opens a new tab. */
export const useOpenChoice = (): Choose => useContext(Ctx) ?? direct;

export function OpenPrefProvider({ children }: { children: ReactNode }) {
  const { data: me } = useOpenPrefs();
  const save = useSavePrefs();
  const [ask, setAsk] = useState<{ group: OpenGroup; name: string; run: Run } | null>(null);
  const [remember, setRemember] = useState(true);
  const primary = useRef<HTMLButtonElement>(null);
  const last = useRef(ask);
  if (ask) last.current = ask;
  const shown = ask ?? last.current; // keeps the text steady through the close fade

  const choose = useCallback<Choose>((group, name, run) => {
    const pref = me?.[KEY[group]]; // ponytail: not loaded yet = ask (harmless)
    if (pref) run(pref);
    else { setRemember(true); setAsk({ group, name, run }); }
  }, [me]);

  function pick(mode: OpenMode) {
    if (!ask) return;
    const { group, run } = ask;
    setAsk(null);
    if (!remember) return run(mode);
    const p = save.mutateAsync({ [KEY[group]]: mode });
    if (mode === "new_tab") { run(mode); p.catch(() => toast.error(SAVE_FAILED)); } // open inside the click
    else p.catch(() => toast.error(SAVE_FAILED)).finally(() => run(mode)); // navigating away would abort the PUT
  }

  return (
    <Ctx.Provider value={choose}>
      {children}
      <Dialog open={ask !== null} onOpenChange={(o) => { if (!o) setAsk(null); }}>
        <DialogContent className="sm:max-w-sm"
          onOpenAutoFocus={(e) => { e.preventDefault(); primary.current?.focus(); }}>
          <DialogHeader>
            <DialogTitle>Open {shown?.name}</DialogTitle>
            <DialogDescription>Choose where it opens.</DialogDescription>
          </DialogHeader>
          <label className="flex min-h-11 items-center gap-2 text-sm">
            <input type="checkbox" className="size-4 accent-primary" checked={remember}
              onChange={(e) => setRemember(e.target.checked)} />
            Remember for all {shown?.group === "workspaces" ? "workspaces" : "apps"}
          </label>
          <DialogFooter>
            <Button variant="outline" onClick={() => pick("same_tab")}>Open here</Button>
            <Button ref={primary} onClick={() => pick("new_tab")}>Open in new tab</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Ctx.Provider>
  );
}
