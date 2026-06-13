import { Button } from "@/components/ui/button";
import { Plus, X } from "lucide-react";

interface Props<T> {
  rows: T[];
  blank: T;
  onChange: (rows: T[]) => void;
  render: (row: T, update: (r: T) => void) => React.ReactNode;
  addLabel?: string;
  disabled?: boolean;
}

export function RepeatableRows<T>({
  rows,
  blank,
  onChange,
  render,
  addLabel = "Add",
  disabled,
}: Props<T>) {
  return (
    <div className="space-y-2">
      {rows.map((row, i) => (
        <div key={i} className="flex items-center gap-2">
          <div className="flex-1">
            {render(row, (r) =>
              onChange(rows.map((x, j) => (j === i ? r : x)))
            )}
          </div>
          <Button
            variant="ghost"
            size="icon"
            aria-label="remove"
            disabled={disabled}
            onClick={() => onChange(rows.filter((_, j) => j !== i))}
          >
            <X className="h-4 w-4" />
          </Button>
        </div>
      ))}
      <Button
        variant="outline"
        size="sm"
        disabled={disabled}
        onClick={() =>
          onChange([...rows, { ...(blank as object) } as T])
        }
      >
        <Plus className="mr-1 h-3 w-3" /> {addLabel}
      </Button>
    </div>
  );
}
