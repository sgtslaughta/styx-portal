/**
 * Coalesce concurrent invocations into a single in-flight call. While one call
 * is pending, every caller receives the SAME promise; once it settles the slot
 * clears and the next call starts fresh.
 *
 * Used for token refresh: the backend rotates refresh tokens with RFC 9700
 * reuse detection, so two parallel /auth/refresh calls would replay a rotated
 * token and revoke the whole family. Single-flight guarantees exactly one.
 */
export function singleFlight<T>(fn: () => Promise<T>): () => Promise<T> {
  let inFlight: Promise<T> | null = null;
  return () => {
    if (!inFlight) {
      inFlight = fn().finally(() => {
        inFlight = null;
      });
    }
    return inFlight;
  };
}
