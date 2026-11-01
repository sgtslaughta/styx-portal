import type { ReactNode } from "react";
import { MoreHorizontal } from "lucide-react";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";

/** The "⋯" menu on desktop tiles and container rows. Details opens the full pane in a side sheet. */
export function RowMenu({ name, onDetails, children }: { name: string; onDetails: () => void; children?: ReactNode }) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button type="button" aria-label={`More actions for ${name}`} onClick={(e) => e.stopPropagation()}
          className="inline-flex size-8 shrink-0 items-center justify-center rounded-md text-muted-foreground hover:bg-accent hover:text-foreground focus-visible:outline-2 focus-visible:outline-ring max-sm:size-11">
          <MoreHorizontal className="size-4" aria-hidden />
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" onClick={(e) => e.stopPropagation()}>
        <DropdownMenuItem onSelect={onDetails}>Details</DropdownMenuItem>
        {children}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
