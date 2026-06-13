import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Label } from "@/components/ui/label";
import { FieldTooltip } from "./field-tooltip";

interface Props {
  label: string;
  value: string;
  options: string[];
  tooltip?: string;
  onChange: (v: string) => void;
  disabled?: boolean;
}

export function EnumSelect({
  label,
  value,
  options,
  tooltip,
  onChange,
  disabled,
}: Props) {
  return (
    <div className="space-y-1.5">
      <Label className="text-xs uppercase tracking-wide text-muted-foreground">
        {label}
        {tooltip && <FieldTooltip text={tooltip} />}
      </Label>
      <Select value={value} onValueChange={onChange} disabled={disabled}>
        <SelectTrigger>
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {options.map((o) => (
            <SelectItem key={o} value={o}>
              {o}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
}
