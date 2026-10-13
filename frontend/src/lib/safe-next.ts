/** First path segments that are Styx's own API/control paths. A cross-site
 * link to /login?next=… becomes a same-site navigation once we follow it, so
 * SameSite=Strict cookies ride along: never follow next into these. Mirrors
 * backend app/security/safe_next.py. */
const BLOCKED = new Set(["api", "internal", "_styx", "login", "logout", "setup",
  "accept-invite", "change-password"]);
const ENCODED_SEP = /%(2e|2f|5c)/i;
const BAD_CHARS = /[\s\x00-\x1f\x7f\\]/;

/** Same-site path from a `?next=` value, else null (no open redirect).
 * Must start with a single "/" (not "//" or "/\", which browsers treat as
 * protocol-relative), contain no whitespace/control characters, no
 * percent-encoded "." "/" "\" and no dot segments, and must not start with a
 * Styx-internal segment (case-insensitive, after percent-decoding). */
export function safeNext(next: string | null | undefined): string | null {
  if (!next || !/^\/(?![/\\])/.test(next) || BAD_CHARS.test(next)) return null;
  const path = next.split(/[?#]/, 1)[0] ?? "";
  try {
    const decoded = decodeURIComponent(path);
    if (ENCODED_SEP.test(path) || ENCODED_SEP.test(decoded) || BAD_CHARS.test(decoded)) return null;
    const segs = decoded.split("/");
    if (segs.includes(".") || segs.includes("..") || BLOCKED.has((segs[1] ?? "").toLowerCase())) return null;
    const u = new URL(next, window.location.origin);
    if (u.origin !== window.location.origin) return null;
    return u.pathname + u.search + u.hash;
  } catch {
    return null;
  }
}
