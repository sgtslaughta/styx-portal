// LinuxServer categories arrive comma-joined ("Media Servers,Music"); split them into single tags.
export const splitCats = (c?: string | null): string[] =>
  [...new Set((c ?? "").split(",").map((s) => s.trim()).filter(Boolean))];

/** Distinct tags ordered by how many images carry them (ties alphabetical). */
export function rankCats(categories: (string | null | undefined)[]): string[] {
  const n = new Map<string, number>();
  for (const c of categories) for (const t of splitCats(c)) n.set(t, (n.get(t) ?? 0) + 1);
  return [...n].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0])).map(([t]) => t);
}
