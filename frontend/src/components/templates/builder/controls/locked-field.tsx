import { cloneElement, isValidElement } from "react";
import { Lock } from "lucide-react";
import { Label } from "@/components/ui/label";

interface Props {
  locked: boolean;
  label: string;
  children: React.ReactNode;
}

export function LockedField({ locked, label, children }: Props) {
  const child = isValidElement(children)
    ? cloneElement(children as React.ReactElement<{ disabled?: boolean }>, locked ? { disabled: true } : {})
    : children;
  return (
    <div className={locked ? "opacity-70" : ""}>
      <Label className="flex items-center gap-1 text-xs">
        {locked && <Lock className="h-3 w-3" />} {label}
        {locked && <span className="text-[10px] text-muted-foreground">(requires admin)</span>}
      </Label>
      {child}
    </div>
  );
}
