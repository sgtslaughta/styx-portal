import { Monitor, Moon, Sun } from "lucide-react";
import { useInstances } from "@/hooks/use-instances";
import { useAuth } from "@/hooks/use-auth";
import { useTheme, type Theme } from "@/theme/ThemeProvider";
import { Tooltip, TooltipTrigger, TooltipContent } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";

function ThemeToggle() {
  const { theme, setTheme } = useTheme();

  function cycle() {
    const order: Theme[] = ["light", "dark", "system"];
    const next = order[(order.indexOf(theme) + 1) % order.length]!;
    setTheme(next);
  }

  const Icon = theme === "dark" ? Moon : theme === "light" ? Sun : Monitor;

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <button onClick={cycle} className="rounded-md p-2 hover:bg-secondary">
          <Icon className="h-4 w-4" />
        </button>
      </TooltipTrigger>
      <TooltipContent>Theme: {theme}</TooltipContent>
    </Tooltip>
  );
}

function CountChip({ count, label, dotClass }: { count: number; label: string; dotClass: string }) {
  if (count === 0) return null;
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span className="flex items-center gap-1.5 rounded-full bg-secondary px-2 py-0.5 text-xs tabular-nums">
          <span className={cn("h-1.5 w-1.5 rounded-full", dotClass)} />
          {count}
        </span>
      </TooltipTrigger>
      <TooltipContent>
        {count} {label} instance{count === 1 ? "" : "s"}
      </TooltipContent>
    </Tooltip>
  );
}

export function Header() {
  const { data: instances } = useInstances();
  const { user, logout } = useAuth();
  const running = instances?.filter((i) => i.status === "running" || i.status === "idle").length ?? 0;
  const paused = instances?.filter((i) => i.status === "paused").length ?? 0;
  const stopped = instances?.filter((i) => i.status === "stopped").length ?? 0;
  const errored = instances?.filter((i) => i.status === "error").length ?? 0;

  return (
    <header className="flex items-center gap-3 border-b border-border px-6 py-2.5">
      <Monitor className="h-5 w-5 text-primary" />
      <span className="text-base font-bold">Styx Portal</span>
      <div className="ml-auto flex items-center gap-1.5">
        <CountChip count={running} label="running" dotClass="bg-success" />
        <CountChip count={paused} label="paused" dotClass="bg-warning" />
        <CountChip count={stopped} label="stopped" dotClass="bg-muted-foreground" />
        <CountChip count={errored} label="error" dotClass="bg-destructive" />
      </div>
      {user && (
        <div className="flex items-center gap-2">
          <span className="text-sm text-muted-foreground">{user.username}</span>
          <button onClick={() => logout()} className="text-sm underline hover:text-foreground">Log out</button>
        </div>
      )}
      <ThemeToggle />
    </header>
  );
}
