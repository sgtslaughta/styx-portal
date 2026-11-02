type Props = { count: number; onSave: () => void; onDiscard: () => void; saving?: boolean };

export function SavePill({ count, onSave, onDiscard, saving }: Props) {
  if (count === 0) return null;
  return (
    <>
    <div aria-hidden="true" className="h-16" />
    <div className="save-pill" role="status" data-testid="save-pill">
      <span>
        <b className="tabular-nums">{count}</b> unsaved {count === 1 ? "change" : "changes"}
      </span>
      <button type="button" className="save-pill-ghost" onClick={onDiscard} disabled={saving}>
        Discard
      </button>
      <button type="button" className="btn-gold" onClick={onSave} disabled={saving}>
        {saving ? "Saving..." : "Save changes"}
      </button>
    </div>
    </>
  );
}
