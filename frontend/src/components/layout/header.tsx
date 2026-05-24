import { Monitor, Moon, Sun } from "lucide-react";
import { useInstances } from "@/hooks/use-instances";
import { useEffect, useState } from "react";

function ThemeToggle() {
  const [dark, setDark] = useState(true);

  useEffect(() => {
    const stored = localStorage.getItem("theme");
    if (stored === "light") {
      setDark(false);
      document.documentElement.classList.remove("dark");
    } else if (stored === "dark" || !stored) {
      setDark(true);
      document.documentElement.classList.add("dark");
    }
  }, []);

  function toggle() {
    const next = !dark;
    setDark(next);
    document.documentElement.classList.toggle("dark", next);
    localStorage.setItem("theme", next ? "dark" : "light");
  }

  return (
    <button onClick={toggle} className="rounded-md p-2 hover:bg-secondary">
      {dark ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
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
