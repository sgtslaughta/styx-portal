const LABELS: Record<string, [string, string]> = {
  requested: ["Update queued", "bg-sky-500/15 text-sky-400"],
  updating: ["Updating…", "bg-sky-500/15 text-sky-400"],
  ok: ["Updated", "bg-emerald-500/15 text-emerald-400"],
  rolled_back: ["Rolled back", "bg-amber-500/15 text-amber-400"],
  failed: ["Update failed", "bg-rose-500/15 text-rose-400"],
};

export function AgentUpdateChip({ state, error }: { state?: string; error?: string | null }) {
  const entry = state ? LABELS[state] : undefined;
  if (!entry) return null;
  return (
    <span title={error ?? undefined} className={`ml-2 rounded px-2 py-0.5 text-xs ${entry[1]}`}>
      {entry[0]}
    </span>
  );
}
