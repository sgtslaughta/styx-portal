import { useEffect, useMemo, useState } from "react";
import { ChevronDown, Search } from "lucide-react";
import { api, ApiError, type Workstation } from "@/api/client";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/common/confirm-dialog";
import { WorkstationSpecs } from "@/components/system/workstation-specs";
import { openConnectWipe } from "@/lib/connect-wipe";
import { cn } from "@/lib/utils";

/* ---------- OS badge: brand-colored glyph keyed off os_info.distro ------- */

const DISTROS: Record<string, { label: string; color: string }> = {
  ubuntu:   { label: "Ub", color: "#E95420" },
  debian:   { label: "De", color: "#A81D33" },
  fedora:   { label: "Fe", color: "#51A2DA" },
  arch:     { label: "Ar", color: "#1793D1" },
  manjaro:  { label: "Mj", color: "#35BF5C" },
  opensuse: { label: "oS", color: "#73BA25" },
  suse:     { label: "SU", color: "#73BA25" },
  linuxmint:{ label: "Mi", color: "#87CF3E" },
  pop:      { label: "Po", color: "#48B9C7" },
  rhel:     { label: "RH", color: "#EE0000" },
  centos:   { label: "Ce", color: "#9CCD2A" },
  rocky:    { label: "Ro", color: "#10B981" },
  almalinux:{ label: "Al", color: "#0F4266" },
  nixos:    { label: "Ni", color: "#5277C3" },
};

function osBadge(ws: Workstation) {
  const distro = String(ws.os_info?.distro ?? "").toLowerCase();
  const key = Object.keys(DISTROS).find((k) => distro.startsWith(k));
  const d = (key && DISTROS[key]) || { label: "Lx", color: "#6B7280" };
  const title = String(ws.os_info?.pretty_name ?? distro ?? "Linux");
  return (
    <span
      title={title}
      className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md text-[11px] font-bold text-white"
      style={{ backgroundColor: d.color }}
    >
      {d.label}
    </span>
  );
}

/* ---------- LED status indicator ----------------------------------------- */

type Led = { color: string; pulse: boolean; label: string };

function ledFor(ws: Workstation): Led {
  if (ws.status === "revoked") return { color: "bg-rose-500", pulse: false, label: "Revoked" };
  if (ws.status !== "online")  return { color: "bg-zinc-500", pulse: false, label: "Offline" };
  if (ws.last_error)           return { color: "bg-rose-400", pulse: true,  label: "Error" };
  if (ws.in_use)               return { color: "bg-amber-400", pulse: true, label: ws.in_use_self ? "Connected (you)" : `In use by ${ws.in_use_by ?? "someone"}` };
  return { color: "bg-emerald-400", pulse: true, label: "Online" };
}

function LedDot({ led }: { led: Led }) {
  return (
    <span className="relative flex h-2.5 w-2.5 shrink-0" title={led.label}>
      {led.pulse && (
        <span className={cn("absolute inline-flex h-full w-full animate-ping rounded-full opacity-50", led.color)} />
      )}
      <span className={cn("relative inline-flex h-2.5 w-2.5 rounded-full", led.color)} />
    </span>
  );
}

/* ---------- list ---------------------------------------------------------- */

type SortKey = "name" | "status" | "seen";
type FilterKey = "all" | "online" | "inuse" | "offline";

const FILTERS: { key: FilterKey; label: string }[] = [
  { key: "all", label: "All" },
  { key: "online", label: "Online" },
  { key: "inuse", label: "In use" },
  { key: "offline", label: "Offline" },
];

function statusRank(ws: Workstation): number {
  if (ws.status === "online" && !ws.in_use) return 0;
  if (ws.status === "online") return 1;
  return 2;
}

function fmtSeen(iso: string | null): string {
  if (!iso) return "never";
  const s = (Date.now() - new Date(iso).getTime()) / 1000;
  if (s < 90) return "just now";
  if (s < 3600) return `${Math.round(s / 60)}m ago`;
  if (s < 86400) return `${Math.round(s / 3600)}h ago`;
  return new Date(iso).toLocaleDateString();
}

export function WorkstationList() {
  const [rows, setRows] = useState<Workstation[]>([]);
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState<SortKey>("status");
  const [filter, setFilter] = useState<FilterKey>("all");
  const [expanded, setExpanded] = useState<string | null>(null);
  const [takeover, setTakeover] = useState<Workstation | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    const load = () => api.myWorkstations().then(setRows).catch(() => {});
    load();
    const t = setInterval(load, 15000);
    return () => clearInterval(t);
  }, []);

  const visible = useMemo(() => {
    const q = query.trim().toLowerCase();
    let out = rows.filter((ws) => {
      if (filter === "online" && !(ws.status === "online" && !ws.in_use)) return false;
      if (filter === "inuse" && !ws.in_use) return false;
      if (filter === "offline" && ws.status === "online") return false;
      if (!q) return true;
      const hay = [ws.name, ws.hostname, String(ws.os_info?.pretty_name ?? ""),
                   String(ws.os_info?.distro ?? "")].join(" ").toLowerCase();
      return hay.includes(q);
    });
    out = [...out].sort((a, b) => {
      if (sort === "name") return a.name.localeCompare(b.name);
      if (sort === "seen")
        return (b.last_heartbeat ?? "").localeCompare(a.last_heartbeat ?? "");
      return statusRank(a) - statusRank(b) || a.name.localeCompare(b.name);
    });
    return out;
  }, [rows, query, sort, filter]);

  if (rows.length === 0) return null;

  const connect = async (ws: Workstation, force = false) => {
    setErr(null);
    try {
      const { url } = await api.workstationConnectUrl(ws.id, force);
      openConnectWipe(url, `Connecting to ${ws.name}…`);
    } catch (e) {
      if (e instanceof ApiError && e.status === 423) setTakeover(ws);
      else setErr((e as Error).message);
    }
  };

  return (
    <section className="space-y-2 mb-4">
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="text-sm font-medium text-muted-foreground mr-auto">Workstations</h3>
        <div className="relative">
          <Search className="absolute left-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search…"
            className="h-7 w-36 rounded-md border border-border bg-background pl-7 pr-2 text-xs focus:outline-none focus:ring-1 focus:ring-ring"
          />
        </div>
        <select
          value={sort}
          onChange={(e) => setSort(e.target.value as SortKey)}
          className="h-7 rounded-md border border-border bg-background px-1.5 text-xs"
          title="Sort"
        >
          <option value="status">Status</option>
          <option value="name">Name</option>
          <option value="seen">Last seen</option>
        </select>
        <div className="flex overflow-hidden rounded-md border border-border text-xs">
          {FILTERS.map((f) => (
            <button
              key={f.key}
              onClick={() => setFilter(f.key)}
              className={cn(
                "px-2 py-1 transition-colors",
                filter === f.key
                  ? "bg-primary text-primary-foreground"
                  : "bg-background text-muted-foreground hover:text-foreground"
              )}
            >
              {f.label}
            </button>
          ))}
        </div>
      </div>

      {err && <p className="text-xs text-rose-400">{err}</p>}

      <ul className="divide-y divide-border rounded-lg border border-border bg-surface">
        {visible.length === 0 && (
          <li className="p-3 text-xs text-muted-foreground">No workstations match.</li>
        )}
        {visible.map((ws) => {
          const led = ledFor(ws);
          const os = ws.os_info as Record<string, string | number | undefined>;
          const isOpen = expanded === ws.id;
          return (
            <li key={ws.id} className="px-3 py-2">
              <div className="flex items-center gap-3">
                <LedDot led={led} />
                {osBadge(ws)}
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium">{ws.name}</p>
                  <p className="truncate text-xs text-muted-foreground">
                    {led.label}
                    {os.pretty_name ? ` · ${os.pretty_name}` : ""}
                    {" · "}seen {fmtSeen(ws.last_heartbeat)}
                  </p>
                </div>
                <button
                  onClick={() => setExpanded(isOpen ? null : ws.id)}
                  className="rounded p-1 text-muted-foreground hover:text-foreground"
                  title="Details"
                  aria-expanded={isOpen}
                >
                  <ChevronDown className={cn("h-4 w-4 transition-transform", isOpen && "rotate-180")} />
                </button>
                <Button
                  size="sm"
                  variant={ws.in_use && !ws.in_use_self ? "secondary" : "default"}
                  disabled={ws.status !== "online"}
                  onClick={() => connect(ws)}
                >
                  {ws.in_use_self ? "Reconnect" : "Connect"}
                </Button>
              </div>
              {isOpen && <WorkstationSpecs ws={ws} className="mt-2 pl-8" />}
            </li>
          );
        })}
      </ul>

      <ConfirmDialog
        open={takeover !== null}
        onOpenChange={(open) => !open && setTakeover(null)}
        title={`Take over "${takeover?.name ?? ""}"?`}
        description={`This workstation is in use by ${takeover?.in_use_by ?? "another user"}. Joining shares the same desktop — you will both see and control the same screen.`}
        confirmLabel="Take over"
        variant="destructive"
        onConfirm={() => {
          if (takeover) {
            connect(takeover, true);
            setTakeover(null);
          }
        }}
      />
    </section>
  );
}
