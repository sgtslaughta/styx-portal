import { createContext, useEffect, useState, type ReactNode } from "react";
import { api } from "@/api/client";

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

  async function logout() {
    await api.logout().catch(() => {});
    setUser(null);
    window.location.href = "/login";
  }

  useEffect(() => { refresh(); }, []);

  return (
    <AuthContext.Provider value={{ user, loading, setupRequired, refresh, logout }}>
      {children}
    </AuthContext.Provider>
  );
}
