/** Small segmented control (Glance .seg-s). */
export function Seg<T extends string>({ label, value, options, disabled, mini, onChange }: {
  label: string; value: T; options: readonly (readonly [T, string])[]; disabled?: boolean; mini?: boolean; onChange: (v: T) => void;
}) {
  return (
    <span className={mini ? "seg-s mini" : "seg-s"} role="group" aria-label={label}>
      {options.map(([v, text]) => (
        <button key={v} type="button" aria-pressed={v === value} disabled={disabled} onClick={() => onChange(v)}>{text}</button>
      ))}
    </span>
  );
}
