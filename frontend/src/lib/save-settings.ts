import { api } from "@/api/client";

type Val = number | boolean | string;
type WithDefault = { key: string; default: unknown; type?: string };

/** Split staged edits: a value equal to the setting's default is a reset (drop the override,
 *  so later default changes still apply); everything else is a normal PATCH. */
export function splitResets(changes: Record<string, Val>, settings: WithDefault[]) {
  // Secrets are never reset: clearing one must write "" (a reset could fall back to an env value).
  const def = new Map(settings.filter((s) => s.type !== "secret").map((s) => [s.key, JSON.stringify(s.default)]));
  const patch: Record<string, Val> = {};
  const resets: string[] = [];
  for (const [k, v] of Object.entries(changes)) {
    if (def.has(k) && def.get(k) === JSON.stringify(v)) resets.push(k);
    else patch[k] = v;
  }
  return { patch, resets };
}

export async function saveSettings(changes: Record<string, Val>, settings: WithDefault[]) {
  const { patch, resets } = splitResets(changes, settings);
  if (Object.keys(patch).length) await api.updateSystemSettings(patch);
  for (const k of resets) await api.resetSystemSetting(k);
}
