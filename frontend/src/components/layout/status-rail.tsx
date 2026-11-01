import { useEffect, useState } from "react";
import { ChevronRight } from "lucide-react";
import { useAuth } from "@/hooks/use-auth";
import { useRailRows, type RailRow } from "@/hooks/use-rail-data";
import { useSystemMetrics } from "@/hooks/use-system";
import { cn } from "@/lib/utils";
import { Dot } from "@/components/common/dot";
import { LoadError } from "@/components/common/load-error";

export const RAIL_W = 320;
export const RAIL_MIN = 56;
const KEY = "styxRail";
const MOBILE = "(max-width: 900px)";
const isMobile = () => typeof matchMedia === "function" && matchMedia(MOBILE).matches;

type Row = RailRow;

const known = (v: number | null | undefined): v is number => typeof v === "number" && Number.isFinite(v);

function Meter({ label, value }: { label: string; value: number | null | undefined }) {
  const v = known(value) ? Math.max(0, Math.min(100, Math.round(value))) : null;
  return (
    <div className="mb-3 text-[13.5px]">
      <div className="mb-1 flex justify-between text-muted-foreground">
        <span>{label}</span><b className="font-semibold tabular-nums text-foreground">{v === null ? "—" : `${v}%`}</b>
      </div>
      <span className="block h-1.5 overflow-hidden rounded-md bg-muted">
        <i className="block h-full rounded-md bg-[var(--s1)]" style={{ width: `${v ?? 0}%` }} />
      </span>
    </div>
  );
}

function List({ rows, empty, ready, error, retry }: { rows: Row[]; empty: string; ready: boolean; error?: boolean; retry: () => void }) {
  if (error && !rows.length) return <LoadError retry={retry} className="mb-6 text-[13px] text-muted-foreground" />;
  if (!ready && !rows.length) return <p className="mb-6 text-[13px] text-muted-foreground">Loading…</p>;
  if (!rows.length) return <p className="mb-6 text-[13px] text-muted-foreground">{empty}</p>;
  return (
    <ul className="mb-6 grid list-none gap-3 p-0 text-sm">
      {rows.slice(0, 3).map((r) => (
        <li key={r.id} className="flex items-baseline gap-2.5">
          <Dot tone={r.tone} />
          <span>{r.text}{r.sub && <small className="block text-[12.5px] text-muted-foreground">{r.sub}</small>}</span>
        </li>
      ))}
    </ul>
  );
}

type Props = { forceCollapsed?: boolean; onOpenAdmin?: () => void; onWidthChange?: (px: number) => void };

export function StatusRail(props: Props) {
  const { user } = useAuth();
  const admin = user?.role === "admin";
  const { onWidthChange } = props;
  useEffect(() => { if (!admin) onWidthChange?.(0); }, [admin, onWidthChange]);
  return admin ? <AdminRail {...props} /> : null;
}

function AdminRail({ forceCollapsed = false, onOpenAdmin, onWidthChange }: Props) {
  const [closed, setClosed] = useState(() => localStorage.getItem(KEY) === "closed" || isMobile());
  const collapsed = forceCollapsed || closed;

  const { data: m } = useSystemMetrics();
  const { active, check, activeReady, checkReady, activeError, checkError, retry } = useRailRows();

  useEffect(() => {
    onWidthChange?.(collapsed || isMobile() ? RAIL_MIN : RAIL_W);
  }, [collapsed, onWidthChange]);

  const toggle = () => {
    const next = !closed;
    setClosed(next);
    localStorage.setItem(KEY, next ? "closed" : "open");
  };

  const cpu = m?.host_cpu_pct;
  const mem = m?.host_ram_pct;
  const disk = m && m.disk_total_gb > 0 ? Math.round((m.disk_used_gb / m.disk_total_gb) * 100) : null;

  return (
    <aside
      aria-label="Server status"
      className="fixed bottom-0 right-0 top-[58px] z-10 overflow-hidden border-l border-border bg-card transition-[width] duration-200 motion-reduce:transition-none"
      style={{ width: collapsed ? RAIL_MIN : RAIL_W }}
    >
      <button
        type="button"
        onClick={toggle}
        disabled={forceCollapsed}
        aria-expanded={!collapsed}
        aria-label={collapsed ? "Expand status panel" : "Collapse status panel"}
        className="absolute left-3 top-3.5 grid h-8 w-8 place-items-center rounded-lg border border-border bg-background text-muted-foreground disabled:opacity-50"
      >
        <ChevronRight size={16} className={cn("transition-transform motion-reduce:transition-none", collapsed && "rotate-180")} />
      </button>
      {collapsed ? (
        <div className="absolute left-0 top-16 flex flex-col items-center gap-4 text-[11px] text-muted-foreground" style={{ width: RAIL_MIN }}>
          <span className="grid justify-items-center gap-1">CPU {known(cpu) ? `${Math.round(cpu)}%` : "—"}</span>
          <span className="grid justify-items-center gap-1">{activeReady ? active.length : "—"} live</span>
          {checkReady && check.length > 0 && (
            <span className="grid justify-items-center gap-1">
              <span className="grid h-5 min-w-5 place-items-center rounded-full bg-destructive px-1.5 text-[11px] font-bold text-white">{check.length}</span>
              to check
            </span>
          )}
        </div>
      ) : (
        <div className="h-full overflow-y-auto py-[18px] pl-[60px] pr-6" style={{ width: RAIL_W }}>
          <h3 className="mb-3 mt-1 text-sm font-semibold">Server</h3>
          <div className="mb-6"><Meter label="CPU" value={cpu} /><Meter label="Memory" value={mem} /><Meter label="Disk" value={disk} /></div>
          <h3 className="mb-3 mt-1 text-sm font-semibold">Active now</h3>
          <List rows={active} empty="Nothing running" ready={activeReady} error={activeError} retry={retry} />
          <h3 className="mb-3 mt-1 text-sm font-semibold">Needs a look</h3>
          <List rows={check} empty="All clear" ready={checkReady} error={checkError} retry={retry} />
          <button type="button" onClick={onOpenAdmin} className="text-[13.5px] text-[var(--s1)] hover:underline">Open admin</button>
        </div>
      )}
    </aside>
  );
}
