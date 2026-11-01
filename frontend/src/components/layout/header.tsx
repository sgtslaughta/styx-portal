import { Monitor, Moon, Sun, Waves } from "lucide-react";
import { useAuth } from "@/hooks/use-auth";
import { useTheme, type Theme } from "@/theme/ThemeProvider";
import { Tooltip, TooltipTrigger, TooltipContent } from "@/components/ui/tooltip";
import { OpeningMenu } from "@/components/layout/opening-menu";
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
        <button onClick={cycle} className="inline-flex size-9 max-sm:size-11 items-center justify-center rounded-md hover:bg-secondary outline-none focus-visible:ring-2 focus-visible:ring-ring" aria-label="Toggle theme">
          <Icon className="h-4 w-4" />
        </button>
      </TooltipTrigger>
      <TooltipContent>Theme: {theme}</TooltipContent>
    </Tooltip>
  );
}

export type HeaderTab = "home" | "admin";

export function Header({ activeTab, onTabChange }: { activeTab: HeaderTab; onTabChange: (tab: HeaderTab) => void }) {
  const { user, logout } = useAuth();
  const tabs: { id: HeaderTab; label: string }[] = [
    { id: "home", label: "Home" },
    // Non-admins have no Admin tab; the same panel serves their account settings.
    { id: "admin", label: user?.role === "admin" ? "Admin" : "Settings" },
  ];

  return (
    <header className="styx-header flex h-[58px] items-center gap-6 border-b border-border px-6">
      <div className="styx-brand flex items-center gap-2.5 text-[15px] font-extrabold tracking-[.08em]">
        <Waves className="h-5 w-5" style={{ color: "var(--brand-accent)" }} />
        STYX PORTAL
      </div>
      <nav className="styx-tabs flex h-full" aria-label="Main">
        {tabs.map((t) => (
          <button
            key={t.id}
            onClick={() => onTabChange(t.id)}
            aria-current={activeTab === t.id ? "page" : undefined}
            className={cn(
              "px-3 font-medium outline-none transition-colors hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring max-sm:min-h-11",
              activeTab === t.id ? "gold-underline text-foreground" : "text-muted-foreground",
            )}
          >
            {t.label}
          </button>
        ))}
      </nav>
      {user && (
        <div className="ml-auto flex items-center gap-2">
          <OpeningMenu username={user.username} />
          <button onClick={() => logout()} className="inline-flex min-h-9 max-sm:min-h-11 items-center rounded-md px-1 text-sm underline underline-offset-2 hover:text-foreground outline-none focus-visible:ring-2 focus-visible:ring-ring">Log out</button>
        </div>
      )}
      <ThemeToggle />
    </header>
  );
}
