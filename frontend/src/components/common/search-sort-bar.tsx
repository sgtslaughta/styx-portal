import * as React from "react";
import { Search } from "lucide-react";

import { cn } from "@/lib/utils";
import { Input } from "@/components/ui/input";

interface SortOption {
  value: string;
  label: string;
}

interface SearchSortBarProps {
  query: string;
  onQueryChange: (q: string) => void;
  placeholder?: string;
  sortOptions?: SortOption[];
  sortBy?: string;
  onSortChange?: (v: string) => void;
  /** Extra filter controls or action buttons rendered at the end. */
  children?: React.ReactNode;
  className?: string;
}

export function SearchSortBar({
  query, onQueryChange, placeholder = "Search…",
  sortOptions, sortBy, onSortChange, children, className,
}: SearchSortBarProps) {
  return (
    <div className={cn("flex flex-wrap items-center gap-2", className)}>
      <div className="relative min-w-48 flex-1">
        <Search className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground" />
        <Input value={query} onChange={(e) => onQueryChange(e.target.value)} placeholder={placeholder} className="pl-8" />
      </div>
      {sortOptions && onSortChange && (
        <select
          value={sortBy}
          onChange={(e) => onSortChange(e.target.value)}
          className="h-9 rounded-md border border-input bg-background px-2 text-sm outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50"
        >
          {sortOptions.map((o) => (
            <option key={o.value} value={o.value}>{o.label}</option>
          ))}
        </select>
      )}
      {children}
    </div>
  );
}
