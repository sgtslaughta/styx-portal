/** Same-site path from a `?next=` value, else null (no open redirect).
 * Must start with a single "/" (not "//" or "/\", which browsers treat as
 * protocol-relative) and contain no whitespace/control characters. */
export function safeNext(next: string | null | undefined): string | null {
  if (!next || !/^\/(?![/\\])/.test(next) || /[\s\x00-\x1f\x7f\\]/.test(next)) return null;
  try {
    const u = new URL(next, window.location.origin);
    if (u.origin !== window.location.origin) return null;
    return u.pathname + u.search + u.hash;
  } catch {
    return null;
  }
}
