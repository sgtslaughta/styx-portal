import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/** Largest two units, minute precision: "6d 5h", "3h 12m", "45m"; seconds only under a minute. */
export function formatDuration(seconds: number | null | undefined): string {
  if (seconds == null || !Number.isFinite(seconds) || seconds < 0) return "—";
  if (seconds < 60) return `${Math.floor(seconds)}s`;
  const s = Math.floor(seconds);
  const d = Math.floor(s / 86_400);
  const h = Math.floor((s % 86_400) / 3600);
  const m = Math.floor((s % 3600) / 60);
  const [big, small] = d ? [`${d}d`, h ? `${h}h` : ""] : h ? [`${h}h`, m ? `${m}m` : ""] : [`${m}m`, ""];
  return small ? `${big} ${small}` : big;
}

export function slugify(text: string): string {
  return text
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "");
}

/** Extract the LinuxServer image short-name from a docker image ref, or null.
 * e.g. "lscr.io/linuxserver/firefox:latest" -> "firefox". Non-LSIO images -> null. */
export function linuxserverImageName(image: string): string | null {
  const m = image.match(/(?:lscr\.io\/)?linuxserver\/([^:@/]+)/i);
  return m ? m[1]! : null;
}

export function shortError(msg: string, max = 140): string {
  return msg.length > max ? msg.slice(0, max - 1) + "…" : msg;
}
