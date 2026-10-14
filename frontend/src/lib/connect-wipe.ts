import { toast } from "sonner";
import type { OpenMode } from "@/api/client";

export const BLOCKED = "Your browser blocked the new tab, so Styx opened it here.";

/** `/connecting` interstitial; the payload rides in the hash (stateless, no storage races). */
const wipe = (p: { url?: string; label: string }) => `/connecting#${encodeURIComponent(JSON.stringify(p))}`;

/** window.open WITHOUT "noopener" (with it the return is always null, so a blocked popup is
 *  undetectable), then cut the opener link by hand. Call synchronously inside a click. */
export function openTab(href: string): Window | null {
  const w = window.open(href, "_blank");
  if (w) w.opener = null;
  return w;
}

/** New tab that plays the wave, then loads `url`. False if the browser blocked it. */
export function openConnectWipe(url: string, label: string): boolean {
  return openTab(wipe({ url, label })) !== null;
}

/** Open a plain link (an app) per the preference; blocked popup -> this tab + toast. */
export function openHref(mode: OpenMode, href: string): void {
  if (mode === "new_tab") {
    if (openTab(href)) return;
    toast(BLOCKED);
  }
  window.location.assign(href);
}

/** Open a session whose URL arrives asynchronously. The tab opens NOW (inside the click, before any
 *  await, so it is not blocked) on a waiting wave; the URL is handed to it once `getUrl` resolves.
 *  On failure the waiting tab is closed and the error is rethrown for the caller's UI. */
export async function openPending(mode: OpenMode, label: string, getUrl: () => Promise<string>): Promise<void> {
  let w: Window | null = null;
  if (mode === "new_tab") {
    w = openTab(wipe({ label }));
    if (!w) toast(BLOCKED);
  }
  let url: string;
  try {
    url = await getUrl();
  } catch (e) {
    w?.close();
    throw e;
  }
  if (w) w.location.replace(wipe({ url, label })); // same path, new hash: no reload, fires hashchange
  else window.location.assign(wipe({ url, label }));
}
