import { Slider } from "@/components/ui/slider";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { FieldTooltip } from "./field-tooltip";

interface Props {
  label: string;
  min: number;
  max: number;
  step?: number;
  value: number;
  unit?: string;
  tooltip?: string;
  onChange: (v: number) => void;
  disabled?: boolean;
}

export function SliderInput({
  label,
  min,
  max,
  step = 1,
  value,
  unit,
  tooltip,
  onChange,
  disabled,
}: Props) {
  return (
    <div className="space-y-2">
      <Label className="text-xs uppercase tracking-wide text-muted-foreground">
        {label}
        {unit ? ` · ${value} ${unit}` : ""}
        {tooltip && <FieldTooltip text={tooltip} />}
      </Label>
      <div className="flex items-center gap-3">
        <Slider
          min={min}
          max={max}
          step={step}
          value={[value]}
          disabled={disabled}
          onValueChange={(v) => onChange(v[0])}
          className="flex-1"
        />
        <Input
          type="number"
          min={min}
          max={max}
          step={step}
          value={value}
          disabled={disabled}
          className="w-20"
          onChange={(e) => onChange(Number(e.target.value))}
        />
      </div>
    </div>
  );
}
