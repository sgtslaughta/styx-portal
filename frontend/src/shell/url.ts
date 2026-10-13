type Mode = "path" | "cookie-root";
const SLUG = /^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$/;
const PREFIX = "/_styx/app/";

function safeInner(p: string): string {
  let decoded: string;
  try { decoded = decodeURIComponent(p); } catch { return "/"; }
  if (!p.startsWith("/") || p.startsWith("//") || /%(2e|2f|5c)/i.test(p) || decoded.includes("\\")
      || decoded.split("/").includes("..")) return "/";
  return p;
}

export function parseShellPath(pathname: string, search: string, hash: string) {
  if (!pathname.startsWith(PREFIX)) return null;
  const rest = pathname.slice(PREFIX.length);
  const slug = rest.split("/", 1)[0] ?? "";
  if (!SLUG.test(slug)) return null;
  const raw = rest.slice(slug.length) || "/";
  const path = safeInner(raw);
  return { slug, inner: path === raw ? path + search + hash : "/" }; // unsafe path: app root, drop query
}

export const frameSrc = (mode: Mode, slug: string, inner: string) =>
  mode === "path" ? `/${slug}${inner}` : inner;

export function shellPathFor(mode: Mode, slug: string,
                             loc: { pathname: string; search: string; hash: string }): string | null {
  let p = loc.pathname;
  if (mode === "path") {
    if (p !== `/${slug}` && !p.startsWith(`/${slug}/`)) return null;
    p = p.slice(slug.length + 1) || "/";
  } else if (p.startsWith("/_styx/") || p.startsWith("/api/") || p === "/login") {
    return null;
  }
  return `${PREFIX}${slug}${p}${loc.search}${loc.hash}`;
}

export function isFrameBlocked(frame: { contentWindow: { location: { href: string } } | null }): boolean {
  try { return !frame.contentWindow || frame.contentWindow.location.href === "about:blank"; }
  catch { return true; }
}

/** True when reading the frame's location throws: a cross-origin document, i.e. the browser's own
 *  error page for a refused frame. about:blank (not committed yet) is deliberately not flagged. */
export function isFrameLocationForbidden(frame: { contentWindow: { location: { href: string } } | null }): boolean {
  try { void frame.contentWindow?.location.href; return false; }
  catch { return true; }
}
