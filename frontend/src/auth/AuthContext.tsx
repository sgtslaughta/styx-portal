import { createContext, useEffect, useState, useRef, useCallback, type ReactNode } from "react";
import { api, ApiError } from "@/api/client";
import { SessionExpiryDialog } from "@/components/auth/SessionExpiryDialog";
import { ActiveSessionDialog } from "@/components/auth/ActiveSessionDialog";

export type AuthUser = { id: string; username: string; email: string | null; role: string };

type AuthState = {
  user: AuthUser | null;
  loading: boolean;
  setupRequired: boolean;
  refresh: () => Promise<void>;
  logout: () => Promise<void>;
};

export const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [loading, setLoading] = useState(true);
  const [setupRequired, setSetupRequired] = useState(false);
  const [showExpiry, setShowExpiry] = useState(false);
  const [showActiveSession, setShowActiveSession] = useState(false);
  const [endingSession, setEndingSession] = useState(false);
  const warnTimer = useRef<number | undefined>(undefined);

  const WARN_AFTER_MS = 13 * 60 * 1000; // warn 2 min before the 15-min access TTL

  const armWarnTimer = useCallback(() => {
    window.clearTimeout(warnTimer.current);
    if (!user) return;
    warnTimer.current = window.setTimeout(() => setShowExpiry(true), WARN_AFTER_MS);
  }, [user]);

  async function refresh() {
    setLoading(true);
    try {
      const s = await api.setupRequired();
      setSetupRequired(s.setup_required);
      if (!s.setup_required) {
        setUser(await api.me().catch(() => null));
      } else {
        setUser(null);
      }
    } finally {
      setLoading(false);
    }
  }

  function finishLogout() {
    setUser(null);
    window.location.href = "/login";
  }

  async function logout() {
    try {
      await api.logout();
    } catch (e) {
      // Active workstation session blocks logout — confirm teardown first.
      if (e instanceof ApiError && e.status === 409) {
        setShowActiveSession(true);
        return;
      }
      // Any other failure: clear locally and leave anyway.
    }
    finishLogout();
  }

  async function endSessionAndLogout() {
    setEndingSession(true);
    await api.logout(true).catch(() => {});
    finishLogout();
  }

  useEffect(() => { refresh(); }, []);

  useEffect(() => {
    if (!user) { window.clearTimeout(warnTimer.current); return; }
    armWarnTimer();
    const reset = () => { if (!showExpiry) armWarnTimer(); };
    const events = ["mousedown", "keydown", "scroll", "touchstart"] as const;
    events.forEach((ev) => window.addEventListener(ev, reset, { passive: true }));
    return () => {
      events.forEach((ev) => window.removeEventListener(ev, reset));
      window.clearTimeout(warnTimer.current);
    };
  }, [user, showExpiry, armWarnTimer]);

  async function staySignedIn() {
    try { await api.refreshSession(); } catch { /* next API call hits the 401 path */ }
    setShowExpiry(false);
    armWarnTimer();
  }

  return (
    <AuthContext.Provider value={{ user, loading, setupRequired, refresh, logout }}>
      {children}
      <SessionExpiryDialog open={showExpiry} onStay={staySignedIn} onSignOut={logout} />
      <ActiveSessionDialog
        open={showActiveSession}
        busy={endingSession}
        onCancel={() => setShowActiveSession(false)}
        onEndAndSignOut={endSessionAndLogout}
      />
    </AuthContext.Provider>
  );
}
