const TONE = { ok: "bg-emerald-500", bad: "bg-destructive", use: "bg-amber-500" } as const;

/** Status dot shared by the rail and the Overview lists. */
export const Dot = ({ tone }: { tone: keyof typeof TONE }) => (
  <span aria-hidden className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${TONE[tone]}`} />
);
