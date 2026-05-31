import { Monitor, Moon, Sun } from "lucide-react";
import { useInstances } from "@/hooks/use-instances";
import { useEffect, useState } from "react";

type Theme = "light" | "dark" | "system";

function applyTheme(theme: Theme) {
  const isDark = theme === "dark" || (theme === "system" && window.matchMedia("(prefers-color-scheme: dark)").matches);
  document.documentElement.classList.toggle("dark", isDark);
}

function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>(() => {
    return (localStorage.getItem("theme") as Theme) ?? "system";
  });

  useEffect(() => {
    applyTheme(theme);
    localStorage.setItem("theme", theme);
  }, [theme]);

  useEffect(() => {
    if (theme !== "system") return;
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const handler = () => applyTheme("system");
    mq.addEventListener("change", handler);
    return () => mq.removeEventListener("change", handler);
  }, [theme]);

  function cycle() {
    const order: Theme[] = ["light", "dark", "system"];
    const next = order[(order.indexOf(theme) + 1) % order.length]!;
    setTheme(next);
  }

  const Icon = theme === "dark" ? Moon : theme === "light" ? Sun : Monitor;

  return (
    <button onClick={cycle} title={`Theme: ${theme}`} className="rounded-md p-2 hover:bg-secondary">
      <Icon className="h-4 w-4" />
    </button>
  );
}

export function Header() {
  const { data: instances } = useInstances();
  const running = instances?.filter((i) => i.status === "running" || i.status === "idle").length ?? 0;
  const stopped = instances?.filter((i) => i.status === "stopped").length ?? 0;

  return (
    <header className="flex items-center gap-4 border-b border-border px-6 py-3">
      <Monitor className="h-5 w-5 text-primary" />
      <span className="text-lg font-bold">Selkies Hub</span>
      <span className="ml-auto text-sm text-muted-foreground">
        {running > 0 && <span className="text-success">{running} running</span>}
        {running > 0 && stopped > 0 && <span> · </span>}
        {stopped > 0 && <span>{stopped} stopped</span>}
      </span>
      <ThemeToggle />
    </header>
  );
}
