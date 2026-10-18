import { useState } from "react";
import { ChevronRight } from "lucide-react";
import type { Group, ProxiedServiceInput, ServicePreset } from "@/api/client";
import { Switch } from "@/components/ui/switch";
import { RISK, RISK_DETAIL, RiskCallout } from "@/components/common/risk-callout";
import { BypassRulesEditor, Field, Section, SwitchRow, selectCls } from "./service-form-parts";
import type { FieldErrors } from "./service-validation";

export const checkCls =
  "h-4 w-4 shrink-0 accent-primary focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring";
const chipCls =
  "flex cursor-pointer items-center gap-2 rounded-md border border-border bg-muted/30 px-2.5 py-1.5 text-sm " +
  "transition-colors hover:bg-accent has-[:checked]:border-primary/50 has-[:checked]:bg-primary/10";

type Props = {
  f: ProxiedServiceInput;
  set: <K extends keyof ProxiedServiceInput>(k: K, v: ProxiedServiceInput[K]) => void;
  preset?: ServicePreset;
  groups: Group[];
  errors: FieldErrors;
};

function mountLine(f: ProxiedServiceInput, preset?: ServicePreset) {
  if (f.mount_mode === "cookie-root") return "Focus: opens full screen";
  if (preset?.subpath) return `Path /${f.slug || "your-slug"}, configured by Styx`;
  return `Path /${f.slug || "your-slug"}, set the app's base path yourself`;
}

export function AccessSection({ f, set, preset, groups, errors }: Props) {
  const [advanced, setAdvanced] = useState(false);
  const native = f.auth_mode === "sso-with-bypass";
  const hasRules = (preset?.bypass_rules.length ?? 0) > 0;
  const switchShown = !!preset && hasRules;
  const bypassErrors = Object.keys(errors).some((k) => k.startsWith("bypass"));
  const showAdvanced = advanced || bypassErrors || (native && !switchShown);
  const showEditor = native && showAdvanced;
  const manual = f.mount_mode === "path" && !preset?.subpath;
  return (
    <Section title="Access" hint="How the app is mounted and who can open it.">
      <p className="text-sm">{mountLine(f, preset)}</p>
      {manual && preset?.base_url_hint && (
        <p className="text-xs text-muted-foreground">App setting: {preset.base_url_hint}</p>
      )}
      {f.mount_mode === "cookie-root" && (
        <RiskCallout tone="warning" title="Takes over this browser" details={RISK_DETAIL.cookieRoot}>{RISK.cookieRoot}</RiskCallout>
      )}
      {preset && hasRules && (
        <SwitchRow id="native-apps" label="Allow native apps" hint={`Let ${preset.name}'s own apps sign in without Styx login.`}>
          <Switch id="native-apps" aria-label="Allow native apps" checked={native}
            onCheckedChange={(v) => {
              set("auth_mode", v ? "sso-with-bypass" : "sso");
              if (v) set("bypass_rules", preset.bypass_rules.map((r) => ({ ...r })));
            }} />
        </SwitchRow>
      )}
      {native && !(showEditor && f.bypass_rules.length > 0) && (
        <RiskCallout title="Some requests skip Styx login">
          {preset && switchShown ? RISK.nativeApps.replace("Jellyfin", preset.name)
            : "Some requests skip Styx login (bypass rules in Advanced). The app's own login is exposed to the internet."}
        </RiskCallout>
      )}
      <SwitchRow id="pass-identity" label="Pass identity" hint="Send the signed-in user to the app.">
        <Switch id="pass-identity" aria-label="Pass identity" checked={f.pass_identity}
          onCheckedChange={(v) => set("pass_identity", v)} />
      </SwitchRow>
      {f.pass_identity && <RiskCallout tone="warning" title="App sees who is signed in">{RISK.passIdentity}</RiskCallout>}
      {f.auth_mode === "app-native" && <RiskCallout title="No Styx login">{RISK.appNative}</RiskCallout>}

      <details className="group space-y-3" open={showAdvanced}>
        <summary className="inline-flex cursor-pointer list-none items-center gap-1 text-sm font-medium [&::-webkit-details-marker]:hidden" onClick={(e) => { e.preventDefault(); setAdvanced(!showAdvanced); }}><ChevronRight className="size-4 transition-transform group-open:rotate-90 motion-reduce:transition-none" aria-hidden />Advanced</summary>
        <div className="mt-3 space-y-3">
          <div className="grid gap-3 sm:grid-cols-2">
            <Field id="mount" label="Mount mode">
              <select id="mount" className={selectCls} value={f.mount_mode}
                onChange={(e) => set("mount_mode", e.target.value as ProxiedServiceInput["mount_mode"])}>
                <option value="path">Path (/slug)</option>
                <option value="cookie-root">Focus (opens full screen)</option>
              </select>
            </Field>
            <Field id="auth" label="Auth mode">
              <select id="auth" className={selectCls} value={f.auth_mode}
                onChange={(e) => set("auth_mode", e.target.value as ProxiedServiceInput["auth_mode"])}>
                <option value="sso">SSO (Styx login required)</option>
                <option value="sso-with-bypass">SSO with bypass rules</option>
                <option value="app-native">App native (no Styx auth)</option>
              </select>
            </Field>
          </div>
          {showEditor && <BypassRulesEditor rules={f.bypass_rules} errors={errors} onChange={(r) => set("bypass_rules", r)} />}
          <SwitchRow id="no-overlay" label="Open without overlay" hint="Open the app full page instead of inside the Styx frame.">
            <Switch id="no-overlay" aria-label="Open without overlay" checked={!f.frame_ok}
              onCheckedChange={(v) => set("frame_ok", !v)} />
          </SwitchRow>
        </div>
      </details>

      <fieldset className="space-y-2">
        <legend className="mb-1.5 text-sm font-medium">Allowed groups</legend>
        {groups.length === 0 ? (
          <p className="text-xs text-muted-foreground">No groups defined. Any logged-in user can open this service. Create groups under Administration, Groups.</p>
        ) : (
          <>
            <div className="flex flex-wrap gap-2">
              {groups.map((g) => (
                <label key={g.id} className={chipCls}>
                  <input type="checkbox" className={checkCls} checked={f.allowed_groups.includes(g.name)}
                    onChange={(e) => set("allowed_groups", e.target.checked
                      ? [...f.allowed_groups, g.name] : f.allowed_groups.filter((n) => n !== g.name))} />
                  {g.name}
                </label>
              ))}
            </div>
            <p className="text-xs text-muted-foreground">Leave all unchecked to allow any logged-in user. Admins always have access.</p>
          </>
        )}
      </fieldset>
    </Section>
  );
}
