import { useQuery } from "@tanstack/react-query";
import { Box } from "lucide-react";
import { toast } from "sonner";
import { api, type Workstation } from "@/api/client";
import { useOpenChoice } from "@/components/open-prompt";
import { WorkstationIcon } from "@/components/system/workstation-icon";
import { openPending } from "@/lib/connect-wipe";
import type { Instance } from "@/lib/types";

type Item = { key: string; name: string; icon: React.ReactNode; status: string; ok: boolean; url: () => Promise<string>; verb: string };

function wsItem(w: Workstation): Item {
  const other = w.in_use && !w.in_use_self;
  const status = w.status !== "online" ? "offline" : w.in_use_self ? "connected (you)"
    : other ? `in use by ${w.in_use_by ?? "someone"}` : "online";
  // ponytail: takeover only from home; the dock just lists someone else's session as unavailable
  return { key: `w${w.id}`, name: w.name, icon: <WorkstationIcon ws={w} />, status, ok: w.status === "online" && !other,
    verb: "Connecting to", url: async () => (await api.workstationConnectUrl(w.id)).url };
}

function instItem(i: Instance): Item {
  return { key: `i${i.id}`, name: i.name, icon: <Box className="size-7 shrink-0 p-1 text-muted-foreground" aria-hidden />,
    status: i.status, ok: i.status === "running" || i.status === "idle",
    verb: "Launching", url: async () => `/desktop/${i.subdomain}` };
}

const DOT = (ok: boolean) => (ok ? "bg-success" : "bg-transparent ring-1 ring-inset ring-muted-foreground");

/** Dock Workspaces list: open per the Workspaces preference; starting/waking stays on home. */
export function DockWorkspaces({ onPicked }: { onPicked: () => void }) {
  const choose = useOpenChoice();
  const ws = useQuery({ queryKey: ["my-workstations"], queryFn: api.myWorkstations, refetchInterval: 30_000 });
  const inst = useQuery({ queryKey: ["instances"], queryFn: api.listInstances, refetchInterval: 30_000 });
  if (ws.isPending || inst.isPending) return <p aria-busy="true" className="py-6 text-muted-foreground">Loading workspaces…</p>;
  const items = [...(ws.data ?? []).map(wsItem), ...(inst.data ?? []).map(instItem)];
  if (items.length === 0 && (ws.isError || inst.isError)) {
    return (
      <div className="flex flex-col items-start gap-2 py-6">
        <p className="text-foreground">Couldn&apos;t load workspaces.</p>
        <button type="button" onClick={() => { void ws.refetch(); void inst.refetch(); }}
          className="inline-flex min-h-11 items-center rounded-md px-3 text-sm font-semibold hover:bg-foreground/10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">Try again</button>
      </div>
    );
  }
  if (items.length === 0) return <p className="py-6 text-foreground">No workspaces yet</p>;
  return (
    <ul className="flex flex-1 flex-col gap-1 overflow-y-auto px-2 py-1">
      {items.map((it) => (
        <li key={it.key}>
          <button type="button" disabled={!it.ok}
            onClick={() => {
              onPicked();
              choose("workspaces", it.name, (mode) => {
                openPending(mode, `${it.verb} ${it.name}…`, it.url).catch((e: Error) => toast.error(e.message || "Couldn't open this workspace"));
              });
            }}
            className="group flex min-h-12 w-full items-center gap-3 rounded-md border border-transparent px-3 text-left hover:bg-foreground/10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:hover:bg-transparent">
            <span className="flex group-disabled:opacity-60">{it.icon}</span>
            <span className="flex-1 truncate group-disabled:opacity-60">{it.name}</span>
            <span className="text-xs text-muted-foreground">{it.status}</span>
            <span className={`size-2.5 rounded-full ${DOT(it.ok)}`} aria-hidden />
          </button>
        </li>
      ))}
    </ul>
  );
}
