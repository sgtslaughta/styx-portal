import { toast } from "sonner";
import { GlassButton } from "@/components/ui/glass-button";
import { DropdownMenuItem } from "@/components/ui/dropdown-menu";
import { StatusBadge } from "@/components/instances/status-badge";
import { useStartInstance, useStopInstance, useUnpauseInstance } from "@/hooks/use-instances";
import { recordOpened } from "@/lib/recents";
import { statusMeta } from "@/lib/status";
import { RowMenu } from "./row-menu";
import type { Instance } from "@/lib/types";

function Icon({ icon }: { icon: string | null }) {
  return icon?.startsWith("http")
    ? <img src={icon} alt="" className="size-5 object-contain" />
    : <span className="text-base leading-none">{icon ?? "🖥️"}</span>;
}

interface Props {
  instances: Instance[];
  icons: Record<string, string | null>;
  onOpen: (i: Instance) => void;
  onDetails: (i: Instance) => void;
}

export function ContainerRows({ instances, icons, onOpen, onDetails }: Props) {
  const start = useStartInstance();
  const stop = useStopInstance();
  const unpause = useUnpauseInstance();
  const fail = (verb: string) => ({ onError: (e: Error) => toast.error(`${verb} failed: ${e.message}`) });

  if (instances.length === 0) return <p className="text-sm text-muted-foreground">No containers yet. Use New container to start one.</p>;
  return (
    <ul className="grid gap-0.5">
      {instances.map((i) => {
        const g = statusMeta(i.status).group;
        const act = g === "running" ? { label: "Connect", run: () => onOpen(i) }
          : g === "paused" ? { label: "Resume", run: () => unpause.mutate(i.id, fail("Resume")) }
          : g === "transition" ? null
          : { label: "Start", run: () => { recordOpened(i.id); start.mutate(i.id, fail("Start")); } };
        return (
          <li key={i.id} className="glass-reveal flex items-center gap-3 rounded-[10px] px-3 py-2.5 hover:bg-card max-sm:grid max-sm:grid-cols-[2rem_minmax(0,1fr)_auto_auto] max-sm:gap-x-2.5 max-sm:gap-y-0 max-sm:[&_.glass]:min-h-10">
            <span className="grid size-8 shrink-0 max-sm:row-span-2 place-items-center rounded-lg bg-secondary"><Icon icon={icons[i.template_id] ?? null} /></span>
            <strong className="min-w-0 flex-1 truncate max-sm:col-start-2 max-sm:row-start-1 max-sm:self-end font-semibold" title={i.name}>{i.name}</strong>
            <span className="ml-auto w-40 text-[13.5px] max-sm:col-start-2 max-sm:row-start-2 max-sm:w-auto"><StatusBadge status={i.status} /></span>
            {act && <span className="max-sm:col-start-3 max-sm:row-span-2 max-sm:row-start-1"><GlassButton tone="teal" onClick={act.run} aria-label={`${act.label} ${i.name}`}>{act.label}</GlassButton></span>}
            <span className="max-sm:col-start-4 max-sm:row-span-2 max-sm:row-start-1"><RowMenu name={i.name} onDetails={() => onDetails(i)}>
              {(g === "running" || g === "paused") && <DropdownMenuItem onSelect={() => stop.mutate(i.id, fail("Stop"))}>Stop</DropdownMenuItem>}
            </RowMenu></span>
          </li>
        );
      })}
    </ul>
  );
}
