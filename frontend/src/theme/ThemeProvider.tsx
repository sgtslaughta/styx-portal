import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { useLocation } from "react-router";
import { isPublicPath, resolveDark, type Theme } from "./resolve";

export type { Theme };

function systemPrefersDark(): boolean {
  return window.matchMedia("(prefers-color-scheme: dark)").matches;
}

type ThemeState = { theme: Theme; setTheme: (t: Theme) => void };

const ThemeContext = createContext<ThemeState | null>(null);

/**
 * App-wide theme controller. Mounted at the root (inside the router) so EVERY
 * route applies the theme and reacts to live OS light/dark changes. Single
 * source of truth for the `.dark` class. Public routes follow the OS; the rest
 * honour the persisted preference.
 */
export function ThemeProvider({ children }: { children: ReactNode }) {
  const { pathname } = useLocation();
  const [theme, setTheme] = useState<Theme>(
    () => (localStorage.getItem("theme") as Theme | null) ?? "system",
  );

  const onPublic = isPublicPath(pathname);

  // Apply the resolved theme on every theme/route change. Persist the user's
  // real preference (not the public-route override).
  useEffect(() => {
    document.documentElement.classList.toggle("dark", resolveDark(pathname, theme, systemPrefersDark()));
    localStorage.setItem("theme", theme);
  }, [theme, pathname]);

  // Live OS changes only matter while the effective theme follows the system:
  // on a public route, or when the stored preference is "system".
  useEffect(() => {
    if (!onPublic && theme !== "system") return;
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const handler = () =>
      document.documentElement.classList.toggle("dark", resolveDark(pathname, theme, mq.matches));
    mq.addEventListener("change", handler);
    return () => mq.removeEventListener("change", handler);
  }, [theme, pathname, onPublic]);

  return <ThemeContext.Provider value={{ theme, setTheme }}>{children}</ThemeContext.Provider>;
}

export function useTheme(): ThemeState {
  const ctx = useContext(ThemeContext);
  if (!ctx) throw new Error("useTheme must be used within ThemeProvider");
  return ctx;
}
