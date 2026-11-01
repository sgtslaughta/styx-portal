import { useQuery } from "@tanstack/react-query";
import { api } from "@/api/client";
import { useInstances } from "@/hooks/use-instances";

export type RailRow = {
  id: string; text: string; sub?: string; tone: "ok" | "bad" | "use";
  /** Needs-a-look: button label + settings section it opens. */
  action?: { label: string; section: string };
  /** Active-now: the instance that "End" stops (workstation sessions have no end action). */
  instanceId?: string; kind?: string;
};

/** Shared by the status rail and the Overview lists: running things and things needing attention. */
export function useRailRows() {
  const { data: instancesData, isSuccess: instOk, isError: instErr, refetch: rInst } = useInstances();
  const instances = instancesData ?? [];
  const { data: wsData, isSuccess: wsOk, isError: wsErr, refetch: rWs } = useQuery({ queryKey: ["workstations"], queryFn: api.listWorkstations, refetchInterval: 30000 });
  const ws = wsData ?? [];
  const { data: svcData, isSuccess: svcOk, isError: svcErr, refetch: rSvc } = useQuery({ queryKey: ["services"], queryFn: api.listServices });
  const services = svcData ?? [];

  const active: RailRow[] = [
    ...instances.filter((i) => i.status === "running").map((i): RailRow => ({ id: `i${i.id}`, text: i.name, sub: "Container running", tone: "ok", instanceId: i.id, kind: "Container" })),
    ...ws.filter((w) => w.in_use).map((w): RailRow => ({ id: `w${w.id}`, text: `${w.in_use_by ?? "Someone"} on ${w.name}`, tone: "ok", kind: "Workstation" })),
  ];
  const check: RailRow[] = [
    ...services.filter((s) => s.needs_setup).map((s): RailRow => ({ id: `s${s.id}`, text: `${s.name} isn't set up`, sub: "Add its address and sign-in", tone: "bad", action: { label: "Set up", section: "services" } })),
    ...instances.filter((i) => i.status === "error").map((i): RailRow => ({ id: `e${i.id}`, text: `${i.name} hit an error`, sub: i.error_message ?? undefined, tone: "bad", action: { label: "View", section: "sessions" } })),
    ...ws.filter((w) => w.status === "offline").map((w): RailRow => ({ id: `o${w.id}`, text: `${w.name} is offline`, tone: "use", action: { label: "View", section: "workstations" } })),
    ...ws.filter((w) => w.agent_outdated && w.status !== "offline").map((w): RailRow => ({ id: `u${w.id}`, text: `${w.name} agent is out of date`, sub: "Updates when it comes online", tone: "use", action: { label: "View", section: "workstations" } })),
  ];
  return {
    active, check, activeReady: instOk && wsOk, checkReady: instOk && wsOk && svcOk,
    activeError: instErr || wsErr, checkError: instErr || wsErr || svcErr,
    retry: () => { void rInst(); void rWs(); void rSvc(); },
  };
}
