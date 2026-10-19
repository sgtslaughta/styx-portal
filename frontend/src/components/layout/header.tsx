import { Monitor, Moon, Sun, Waves } from "lucide-react";
import { useAuth } from "@/hooks/use-auth";
import { useTheme, type Theme } from "@/theme/ThemeProvider";
import { Tooltip, TooltipTrigger, TooltipContent } from "@/components/ui/tooltip";
import { OpeningMenu } from "@/components/layout/opening-menu";

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
        <button onClick={cycle} className="inline-flex size-9 max-sm:size-11 items-center justify-center rounded-md hover:bg-secondary outline-none focus-visible:ring-2 focus-visible:ring-ring" aria-label="Toggle theme">
          <Icon className="h-4 w-4" />
        </button>
      </TooltipTrigger>
      <TooltipContent>Theme: {theme}</TooltipContent>
    </Tooltip>
  );
}

export function Header() {
  const { user, logout } = useAuth();

  return (
    <header className="styx-header styx-motif flex items-center gap-3 border-b border-border px-6 py-2.5 max-sm:px-4">
      <Waves className="h-5 w-5" style={{ color: "var(--brand-accent)" }} />
      <span className="text-base font-extrabold tracking-wider">STYX PORTAL</span>
      <div className="ml-auto flex items-center gap-2">
        {user && <OpeningMenu username={user.username} onLogout={() => void logout()} />}
        <ThemeToggle />
      </div>
    </header>
  );
}
