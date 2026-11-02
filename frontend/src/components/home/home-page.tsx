import { useEffect, useMemo, useState } from "react";
import { Plus } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/api/client";
import { SectionHead } from "@/components/common/section-head";
import { useInstances, useStartInstance, useUnpauseInstance } from "@/hooks/use-instances";
import { useTemplates } from "@/hooks/use-templates";
import { useOpenInstance, useWorkstationConnect } from "@/hooks/use-open-actions";
import { OPENED_EVENT, readOpened, recentItems, recordOpened, type RecentItem } from "@/lib/recents";
import { AppsGrid } from "./apps-grid";
import { ContainerRows } from "./container-rows";
import { DesktopTiles } from "./desktop-tiles";
import { DetailsSheet, type Detail } from "./details-sheet";
import { RecentStrip } from "./recent-strip";

export function HomePage({ onNewContainer, onOpenSettings }: { onNewContainer: () => void; onOpenSettings?: () => void }) {
  const { data: instances = [] } = useInstances();
  const { data: templates } = useTemplates();
  const { data: workstations = [] } = useQuery({ queryKey: ["my-workstations"], queryFn: api.myWorkstations, refetchInterval: 15000 });
  const { connect, error, dialog } = useWorkstationConnect();
  const openInstance = useOpenInstance();
  const start = useStartInstance();
  const unpause = useUnpauseInstance();
  const [detail, setDetail] = useState<Detail | null>(null);
  const [opened, setOpened] = useState(readOpened);

  const icons = useMemo(() => Object.fromEntries((templates ?? []).map((t) => [t.id, t.icon ?? null])), [templates]);
  const recents = useMemo(() => recentItems(instances, workstations, opened), [instances, workstations, opened]);
  useEffect(() => {
    const refresh = () => setOpened(readOpened());
    window.addEventListener(OPENED_EVENT, refresh);
    return () => window.removeEventListener(OPENED_EVENT, refresh);
  }, []);

  function actOnRecent(r: RecentItem) {
    if (r.kind === "desktop") {
      const ws = workstations.find((w) => w.id === r.id);
      if (ws) connect(ws);
    } else {
      const i = instances.find((x) => x.id === r.id);
      if (!i) return;
      if (r.action === "Start") { recordOpened(i.id); start.mutate(i.id); }
      else if (i.status === "paused") unpause.mutate(i.id);
      else openInstance(i);
    }
  }

  return (
    <div className="mx-auto max-w-[1200px] space-y-6 pb-16 md:space-y-9">
      <section aria-label="Recent">
        <SectionHead title="Recent" />
        <RecentStrip items={recents} onAct={actOnRecent} />
      </section>
      <section aria-label="Desktops">
        <SectionHead title="Desktops" />
        {error && <p className="mb-2 text-xs text-destructive">{error}</p>}
        <DesktopTiles workstations={workstations} onConnect={connect} onDetails={(ws) => setDetail({ kind: "desktop", ws })} />
      </section>
      <section>
        <SectionHead title="Apps" />
        <AppsGrid onOpenSettings={onOpenSettings} />
      </section>
      <section aria-label="Containers">
        <SectionHead
          title="Containers"
          note={<span className="max-sm:hidden">stop on their own after 30 min idle</span>}
          action={
            <button type="button" onClick={onNewContainer}
              className="inline-flex shrink-0 whitespace-nowrap max-sm:ml-auto max-sm:min-h-10 items-center gap-2 rounded-[9px] bg-[#2A767C] py-2 pr-3.5 pl-2.5 text-sm font-semibold text-[#F7F9F8] shadow-[inset_0_1px_0_rgba(255,255,255,.18),0_1px_2px_rgba(0,0,0,.25),0_0_0_1px_rgba(111,183,188,.35)] hover:bg-[#318890] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring">
              <span aria-hidden="true" className="grid size-[22px] place-items-center rounded-md bg-white/15"><Plus className="size-4" /></span>
              New container
            </button>
          }
        />
        <p className="-mt-2 mb-3 text-[13px] text-muted-foreground sm:hidden">Stop on their own after 30 min idle.</p>
        <ContainerRows instances={instances} icons={icons} onOpen={openInstance} onDetails={(i) => setDetail({ kind: "container", id: i.id, name: i.name })} />
      </section>
      <DetailsSheet detail={detail} onClose={() => setDetail(null)} />
      {dialog}
    </div>
  );
}
