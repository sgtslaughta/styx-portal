import { createContext, useEffect, useState, useRef, type ReactNode } from "react";
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
  const lastActivity = useRef<number>(Date.now());

  const WARN_AFTER_MS = 13 * 60 * 1000;   // show the warning after this much idle
  const LOGOUT_AFTER_MS = 15 * 60 * 1000; // force sign-out after this much idle

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

  async function idleLogout() {
    // Genuinely idle: revoke the refresh token server-side, then redirect.
    // No active session can exist here (it would have reset the idle timer).
    await api.logout().catch(() => {});
    finishLogout();
  }

  useEffect(() => { refresh(); }, []);

  // Idle tracking. Local input counts as activity — and so does an active
  // streaming session in another window. The desktop runs in a separate,
  // non-React page, so we can't see its input events; we read its liveness from
  // the backend (in_use_self) instead. client.ts silently refreshes tokens on
  // demand, so the session ends ONLY when the user is idle here AND streaming
  // nowhere.
  useEffect(() => {
    if (!user) return;
    lastActivity.current = Date.now();
    const bump = () => { lastActivity.current = Date.now(); setShowExpiry(false); };
    const events = ["mousedown", "keydown", "scroll", "touchstart"] as const;
    events.forEach((ev) => window.addEventListener(ev, bump, { passive: true }));

    const tick = async () => {
      const ws = await api.myWorkstations().catch(() => []);
      if (ws.some((w) => w.in_use_self)) lastActivity.current = Date.now();
      const idle = Date.now() - lastActivity.current;
      if (idle >= LOGOUT_AFTER_MS) void idleLogout();
      else setShowExpiry(idle >= WARN_AFTER_MS);
    };
    const id = window.setInterval(tick, 30_000);
    return () => {
      events.forEach((ev) => window.removeEventListener(ev, bump));
      window.clearInterval(id);
    };
  }, [user]);

  async function staySignedIn() {
    try { await api.refreshSession(); } catch { /* next API call triggers silent refresh */ }
    lastActivity.current = Date.now();
    setShowExpiry(false);
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
