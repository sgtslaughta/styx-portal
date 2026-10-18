import { ChevronDown, UserRound } from "lucide-react";
import { toast } from "sonner";
import { useOpenPrefs, useSavePrefs } from "@/components/open-prompt";
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuLabel, DropdownMenuRadioGroup, DropdownMenuRadioItem,
  DropdownMenuSeparator, DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

const ROWS = [["open_workspaces", "Workspaces"], ["open_apps", "Apps"]] as const;

/** Username dropdown: where Workspaces and Apps open (New tab / This tab / Ask). Saves on change. */
export function OpeningMenu({ username }: { username: string }) {
  const { data: me, isPending } = useOpenPrefs();
  const save = useSavePrefs();
  const set = (key: (typeof ROWS)[number][0], v: string) =>
    save.mutate({ [key]: v === "ask" ? null : v } as Parameters<typeof save.mutate>[0], {
      onSuccess: () => toast.success("Opening preference saved"),
      onError: () => toast.error("Couldn't save your choice"),
    });
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button aria-label={`Account menu, ${username}`} disabled={isPending}
          className="inline-flex min-h-9 max-sm:min-h-11 items-center gap-1 rounded-md px-2 text-sm text-muted-foreground hover:text-foreground outline-none focus-visible:ring-2 focus-visible:ring-ring">
          <UserRound className="size-4" aria-hidden />
          <span className="max-sm:hidden">{username}</span>
          <ChevronDown className="size-3.5" aria-hidden />
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-56">
        <DropdownMenuLabel>Opening</DropdownMenuLabel>
        {ROWS.map(([key, label], i) => (
          <div key={key}>
            {i > 0 && <DropdownMenuSeparator />}
            <DropdownMenuLabel className="text-xs font-normal text-muted-foreground">{label}</DropdownMenuLabel>
            <DropdownMenuRadioGroup aria-label={label} value={me?.[key] ?? "ask"} onValueChange={(v) => set(key, v)}>
              <DropdownMenuRadioItem value="new_tab">New tab</DropdownMenuRadioItem>
              <DropdownMenuRadioItem value="same_tab">This tab</DropdownMenuRadioItem>
              <DropdownMenuRadioItem value="ask">Ask</DropdownMenuRadioItem>
            </DropdownMenuRadioGroup>
          </div>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
