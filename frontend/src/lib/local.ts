/** localStorage that never throws (private mode, blocked storage): reads fall back to null, writes are dropped. */
export function readLocal(key: string): string | null {
  try { return localStorage.getItem(key); } catch { return null; }
}

/** `null` removes the key. */
export function writeLocal(key: string, value: string | null): void {
  try {
    if (value === null) localStorage.removeItem(key);
    else localStorage.setItem(key, value);
  } catch { /* storage blocked: session-only */ }
}
