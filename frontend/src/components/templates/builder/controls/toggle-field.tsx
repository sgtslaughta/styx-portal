import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";
import { FieldTooltip } from "./field-tooltip";

interface Props {
  label: string;
  checked: boolean;
  tooltip?: string;
  onChange: (v: boolean) => void;
  disabled?: boolean;
}

export function ToggleField({
  label,
  checked,
  tooltip,
  onChange,
  disabled,
}: Props) {
  return (
    <div className="flex items-center gap-3">
      <Switch
        checked={checked}
        onCheckedChange={onChange}
        disabled={disabled}
      />
      {label && (
        <Label className="text-sm">
          {label}
          {tooltip && <FieldTooltip text={tooltip} />}
        </Label>
      )}
    </div>
  );
}
