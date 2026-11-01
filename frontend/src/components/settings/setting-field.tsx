import "@/styles/settings-grid.css";
import type { Setting, SettingValue } from "@/api/client";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { useState } from "react";
import { SizePresetsDialog, type Preset } from "./size-presets-dialog";
import { cleanLabel, divisor, fromDisplay, parseRate, toDisplay, unitOf } from "./units";

type Props = {
  setting: Setting;
  /** Current (possibly unsaved) value; undefined = untouched. */
  value: SettingValue | undefined;
  error?: string;
  disabled: boolean;
  onChange: (value: SettingValue) => void;
  /** ↺ — drop the unsaved edit. */
  onRestore: () => void;
  onResetDefault: () => void;
  onClear: () => void;
};

const same = (a: SettingValue | undefined, b: SettingValue) =>
  a === b || (typeof a === "object" && typeof b === "object" ? JSON.stringify(a) === JSON.stringify(b) : String(a) === String(b));

export function isChanged(s: Setting, v: SettingValue | undefined): boolean {
  if (v === undefined) return false;
  return s.type === "secret" ? v !== "" : !same(v, s.value);
}

function PresetsControl({ cur, disabled, onChange }: { cur: SettingValue | undefined; disabled: boolean; onChange: (v: SettingValue) => void }) {
  const [open, setOpen] = useState(false);
  const list = (Array.isArray(cur) ? cur : []) as unknown as Preset[];
  return (
    <>
      <button type="button" className="linkbtn" disabled={disabled} onClick={() => setOpen(true)}>Edit {list.length} sizes</button>
      <SizePresetsDialog open={open} presets={list} onOpenChange={setOpen} onApply={(p) => onChange(p as unknown as SettingValue)} />
    </>
  );
}

function Control({ setting, value, error, disabled, onChange }: Props) {
  const { type, key } = setting;
  const label = cleanLabel(key, setting.label);
  const cur = value === undefined ? (type === "secret" ? "" : setting.value) : value;
  if (type === "bool") {
    return (
      <input type="checkbox" role="switch" aria-label={label} checked={Boolean(cur)} disabled={disabled}
        onChange={(e) => onChange(e.target.checked)} />
    );
  }
  if (type === "json") return <PresetsControl cur={cur} disabled={disabled} onChange={onChange} />;
  if (type === "enum") {
    return (
      <div className="in">
        <select aria-label={label} value={String(cur ?? "")} disabled={disabled} onChange={(e) => onChange(e.target.value)}>
          {(setting.choices ?? []).map((c) => <option key={c} value={c}>{c}</option>)}
        </select>
      </div>
    );
  }
  // Rate period S always comes from the stored value, so an empty/invalid N keeps its unit.
  const period = type === "rate" ? (parseRate(setting.value) ?? parseRate(setting.default))?.s : undefined;
  const rate = period !== undefined;
  const numeric = type === "int" || rate;
  const shownRaw = value === null ? "" : cur;
  let shown = String(shownRaw ?? "");
  let unit = unitOf(key);
  if (rate) unit = toDisplay(key, `0/${period}`).unit;
  if (numeric && shownRaw !== "" && shownRaw !== null && (type === "int" || parseRate(shownRaw))) {
    const d = toDisplay(key, shownRaw);
    shown = String(+d.value.toFixed(4));
    unit = d.unit;
  } else if (rate) shown = "";
  const edit = (txt: string) => {
    if (!numeric || txt === "") return onChange(numeric ? "" : txt);
    const num = Number(txt);
    if (Number.isNaN(num)) return;
    onChange(rate ? `${Math.round(num)}/${period}` : fromDisplay(key, num));
  };
  const d = divisor(key);
  return (
    <div className={error ? "in invalid" : "in"} title={error}>
      <input
        className={numeric ? "no-spin" : undefined}
        type={secretOrText(type, numeric)}
        step={numeric ? "any" : undefined}
        aria-label={label}
        aria-invalid={error ? true : undefined}
        autoComplete={type === "secret" ? "new-password" : undefined}
        value={shown}
        disabled={disabled}
        placeholder={type === "secret" ? (value === null ? "Will be cleared on save" : setting.is_set ? "Set - type to replace" : "Not set") : String(toDisplay(key, setting.default).value || setting.default || "")}
        min={type === "int" && setting.min !== null ? setting.min / d : undefined}
        max={type === "int" && setting.max !== null ? setting.max / d : undefined}
        onChange={(e) => edit(e.target.value)}
      />
      {unit && <em>{unit}</em>}
    </div>
  );
}

const secretOrText = (type: string, numeric: boolean) => (type === "secret" ? "password" : numeric ? "number" : "text");

export function SettingField(props: Props) {
  const { setting, value, disabled, error, onRestore, onResetDefault, onClear } = props;
  const changed = isChanged(setting, value);
  const secret = setting.type === "secret";
  const wide = setting.type === "enum" || setting.type === "str" || secret || setting.type === "json";
  const canReset = !changed && !secret && setting.type !== "json" && !same(setting.value, setting.default);
  return (
    <div className={`row${wide ? " wide" : ""}${changed ? " changed" : ""}${setting.type === "bool" ? " sw" : ""}`} data-changed={changed || undefined}>
      <span>
        {cleanLabel(setting.key, setting.label)}
        {setting.help && (
          <TooltipProvider>
            <Tooltip>
              <TooltipTrigger asChild>
                <button type="button" className="help" aria-label={`About ${setting.label}`}>?</button>
              </TooltipTrigger>
              <TooltipContent side="right" className="max-w-xs">{setting.help}</TooltipContent>
            </Tooltip>
          </TooltipProvider>
        )}
        {canReset && (
          <button type="button" className="link-reset" onClick={onResetDefault} disabled={disabled}>
            Reset to default
          </button>
        )}
        {secret && <small className="link-reset" style={{ opacity: 1, textDecoration: "none" }}>{setting.is_set ? "Set" : "Not set"}</small>}
        {secret && setting.is_set && value !== null && (
          <button type="button" className="link-reset" onClick={onClear} disabled={disabled}>Clear</button>
        )}
        {error && <small className="row-err">{error}</small>}
      </span>
      <Control {...props} />
      <button type="button" className="reset" onClick={onRestore} aria-label={`Restore ${setting.label}`} title="Restore saved value" tabIndex={changed ? 0 : -1}>
        {changed ? "↺" : ""}
      </button>
    </div>
  );
}
