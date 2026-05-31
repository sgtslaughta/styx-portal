import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatDuration(seconds: number | null | undefined): string {
  if (seconds == null || seconds < 0) return "—";
  if (seconds < 60) return `${Math.floor(seconds)}s`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m`;
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  return m > 0 ? `${h}h ${m}m` : `${h}h`;
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
