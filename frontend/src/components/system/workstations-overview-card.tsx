import { useQuery } from "@tanstack/react-query";
import { api } from "@/api/client";
import { OverviewCard, Figure, type Level } from "./overview-cards";

export function WorkstationsOverviewCard() {
  const { data: rows = [] } = useQuery({
    queryKey: ["workstations"], queryFn: api.listWorkstations, refetchInterval: 30000,
  });
  const n = (f: (w: (typeof rows)[number]) => boolean) => rows.filter(f).length;
  const online = n((w) => w.status === "online");
  const offline = n((w) => w.status === "offline");
  const error = n((w) => w.status === "error");
  const outdated = n((w) => w.agent_outdated);
  const badUpdate = n((w) => w.update_state === "rolled_back" || w.update_state === "failed");
  const users = [...new Set(rows.filter((w) => w.in_use && w.in_use_by).map((w) => w.in_use_by as string))];
  const inUse = n((w) => w.in_use);
  const webrtc = n((w) => w.stream_settings?.transport === "webrtc");
  const level: Level = error > 0 || badUpdate > 0 ? "error" : offline > 0 || outdated > 0 ? "warn" : "ok";
  return (
    <OverviewCard section="workstations" level={level}>
      <Figure label="Online / offline / error" value={`${online} / ${offline} / ${error}`} />
      <Figure label="In use" value={inUse ? `${inUse}${users.length ? ` (${users.slice(0, 2).join(", ")})` : ""}` : "0"} />
      <Figure label="Agents out of date" value={outdated} />
      {badUpdate > 0 && <Figure label="Updates rolled back / failed" value={badUpdate} />}
      <Figure label="Transport" value={`${webrtc} WebRTC / ${rows.length - webrtc} other`} />
    </OverviewCard>
  );
}
