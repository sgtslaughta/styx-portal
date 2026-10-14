import { useEffect, useState } from "react";
import { Toaster, type ToasterProps } from "sonner";

/** Toaster that follows the app theme by mirroring the `.dark` class on <html>
 * (the single source of truth applyTheme toggles for light/dark/system). */
export function ThemedToaster(props: Omit<ToasterProps, "theme">) {
  const [isDark, setIsDark] = useState(() =>
    document.documentElement.classList.contains("dark"),
  );
  useEffect(() => {
    const el = document.documentElement;
    const obs = new MutationObserver(() => setIsDark(el.classList.contains("dark")));
    obs.observe(el, { attributes: true, attributeFilter: ["class"] });
    return () => obs.disconnect();
  }, []);
  return <Toaster {...props} theme={isDark ? "dark" : "light"} />;
}
