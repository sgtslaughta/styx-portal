import { useEffect, useState } from "react";
import type { DiscoveredContainer, Group, ProxiedService, ProxiedServiceInput, ServicePreset } from "@/api/client";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { DrawerBody, DrawerFooter } from "@/components/ui/drawer";
import { RISK, RISK_DETAIL, RiskCallout } from "@/components/common/risk-callout";
import { BypassRulesEditor, Field, Section, SwitchRow, selectCls } from "./service-form-parts";
import { validateService, type FieldErrors } from "./service-validation";

const EMPTY: ProxiedServiceInput = {
  slug: "", name: "", icon: null, kind: "url", upstream_url: "", container: null, container_port: null,
  mount_mode: "path", auth_mode: "sso", bypass_rules: [], allowed_groups: [], verify_tls: true,
  health_path: null, preset_id: null, enabled: true, pass_identity: false, frame_ok: true,
};
const ACK_TEXT =
  "I understand that this app runs on the same origin as Styx: any JavaScript it serves can use Styx with the rights of whoever opens it.";
const checkCls =
  "h-4 w-4 shrink-0 accent-primary focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring";
const chipCls =
  "flex cursor-pointer items-center gap-2 rounded-md border border-border bg-muted/30 px-2.5 py-1.5 text-sm " +
  "transition-colors hover:bg-accent has-[:checked]:border-primary/50 has-[:checked]:bg-primary/10";
const KNOWN = ["slug", "name", "upstream_url", "container", "container_port", "health_path", "icon"];

export type DiscoveredPrefill = { name: string; port?: number; preset: string | null };
type Props = {
  initial?: ProxiedService; presets: ServicePreset[]; groups: Group[]; discovered?: DiscoveredPrefill | null;
  loadContainers?: () => Promise<DiscoveredContainer[]>;
  /** Resolve with field errors to show them next to their fields; throw/reject is not expected. */
  onSubmit: (data: ProxiedServiceInput) => void | FieldErrors | Promise<void | FieldErrors>;
  onCancel: () => void;
};

function withPreset(f: ProxiedServiceInput, p: ServicePreset): ProxiedServiceInput {
  return {
    ...f, preset_id: p.id, slug: f.slug || p.id, name: f.name || p.name, icon: p.icon,
    mount_mode: p.mount_mode, auth_mode: p.auth_mode, health_path: p.health_path, verify_tls: p.verify_tls,
    bypass_rules: p.bypass_rules.map((r) => ({ ...r })),
    container_port: f.kind === "docker-local" ? (f.container_port ?? p.default_port) : f.container_port,
  };
}

function initialState(initial: Props["initial"], discovered: Props["discovered"], presets: ServicePreset[]) {
  if (initial) {
    const { id: _i, upstream_fallback: _u, health_status: _h, health_checked_at: _c, created_at: _a, updated_at: _b, ...rest } = initial;
    return rest;
  }
  if (discovered) {
    const base: ProxiedServiceInput = {
      ...EMPTY, kind: "docker-local", upstream_url: null, container: discovered.name, container_port: discovered.port ?? null,
      slug: discovered.name.toLowerCase().replace(/[^a-z0-9-]/g, "-").replace(/^-+|-+$/g, ""), name: discovered.name,
    };
    const p = presets.find((x) => x.id === discovered.preset);
    return p ? withPreset(base, p) : base;
  }
  return EMPTY;
}

export function ServiceForm({ initial, presets, groups, discovered, loadContainers, onSubmit, onCancel }: Props) {
  const isEdit = !!initial;
  const [f, setF] = useState<ProxiedServiceInput>(() => initialState(initial, discovered, presets));
  const [touched, setTouched] = useState<Set<string>>(new Set());
  const [srv, setSrv] = useState<FieldErrors>({});
  const [saving, setSaving] = useState(false);
  const [ack, setAck] = useState(false); // never pre-checked, not even on edit
  const [containers, setContainers] = useState<DiscoveredContainer[] | null>(null);
  const [discoverErr, setDiscoverErr] = useState<string | null>(null);

  useEffect(() => {
    if (f.kind !== "docker-local" || !loadContainers || containers !== null) return;
    let live = true;
    loadContainers().then((c) => { if (live) setContainers(c); })
      .catch((e: unknown) => { if (live) { setContainers([]); setDiscoverErr(e instanceof Error ? e.message : "Discovery failed"); } });
    return () => { live = false; };
  }, [f.kind, loadContainers, containers]);

  const touch = (k: string) => setTouched((t) => new Set(t).add(k));
  const set = <K extends keyof ProxiedServiceInput>(k: K, v: ProxiedServiceInput[K]) => {
    setF((p) => ({ ...p, [k]: v }));
    touch(k);
    setSrv((s) => { if (!(k in s)) return s; const { [k]: _x, ...rest } = s; return rest; });
  };
  const preset = presets.find((p) => p.id === f.preset_id) ?? null;
  const errors = validateService(f, isEdit);
  const valid = Object.keys(errors).length === 0;
  const err = (k: string) => srv[k] ?? (touched.has(k) ? errors[k] : undefined);
  const aria = (k: string) => ({ "aria-invalid": !!err(k) || undefined, "aria-describedby": err(k) ? `${k}-err` : undefined });
  const stray = Object.entries(srv).filter(([k]) => !KNOWN.includes(k));

  const applyPreset = (id: string) => {
    const p = presets.find((x) => x.id === id);
    if (p) setF(withPreset(f, p)); else set("preset_id", null);
  };
  const setKind = (kind: ProxiedServiceInput["kind"]) =>
    setF({ ...f, kind, ...(kind === "url"
      ? { container: null, container_port: null, upstream_url: "" }
      : { upstream_url: null }) });
  const pickContainer = (name: string) => {
    const c = containers?.find((x) => x.name === name);
    setF((p) => ({ ...p, container: name || null, container_port: c?.ports[0] ?? p.container_port }));
    touch("container");
  };

  const submit = async () => {
    if (!valid || !ack || saving) return;
    setSaving(true);
    try {
      const res = await onSubmit({ ...f, name: f.name.trim(), bypass_rules: f.auth_mode === "sso-with-bypass" ? f.bypass_rules : [] });
      if (res) setSrv(res);
    } finally { setSaving(false); }
  };
  const ports = containers?.find((c) => c.name === f.container)?.ports ?? [];

  return (
    <form className="flex min-h-0 flex-1 flex-col" noValidate onSubmit={(e) => { e.preventDefault(); void submit(); }}>
      <DrawerBody className="space-y-5">
        <Section title="Basics">
          <Field id="preset" label="Preset" hint={preset?.base_url_hint ? `App setting: ${preset.base_url_hint}` : "Optional: prefills mode, auth, health and bypass rules."}>
            <select id="preset" className={selectCls} value={f.preset_id ?? ""} autoFocus={!isEdit && !discovered}
              onChange={(e) => applyPreset(e.target.value)}>
              <option value="">None (custom)</option>
              {presets.map((p) => <option key={p.id} value={p.id}>{p.icon ? `${p.icon} ` : ""}{p.name}</option>)}
            </select>
          </Field>
          {preset?.warnings.map((w) => <RiskCallout key={w} tone="warning" title={`${preset.name} note`}>{w}</RiskCallout>)}
          <div className="grid gap-3 sm:grid-cols-2">
            <Field id="name" label="Name" error={err("name")}>
              <Input id="name" value={f.name} autoComplete="off" {...aria("name")} onChange={(e) => set("name", e.target.value)} />
            </Field>
            <Field id="slug" label="Slug" error={err("slug")}
              hint={isEdit ? "Fixed after creation." : f.slug ? `Opens at /${f.slug}` : "URL path, e.g. jellyfin"}>
              <Input id="slug" value={f.slug} disabled={isEdit} autoComplete="off" {...aria("slug")} onBlur={() => touch("slug")}
                onChange={(e) => set("slug", e.target.value)} />
            </Field>
          </div>
          <SwitchRow id="enabled" label="Enabled" hint="When off, the service keeps its settings but is not reachable.">
            <Switch id="enabled" aria-label="Enabled" checked={f.enabled} onCheckedChange={(v) => set("enabled", v)} />
          </SwitchRow>
        </Section>

        <Section title="Upstream" hint="Where Styx forwards requests for this service.">
          <Field id="kind" label="Kind">
            <select id="kind" className={selectCls} value={f.kind} onChange={(e) => setKind(e.target.value as ProxiedServiceInput["kind"])}>
              <option value="url">URL (any host:port)</option>
              <option value="docker-local">Local docker container</option>
            </select>
          </Field>
          {f.kind === "url" ? (
            <Field id="upstream" label="Upstream URL" error={err("upstream_url")}>
              <Input id="upstream" placeholder={`http://192.168.1.10:${preset?.default_port ?? 8080}`} value={f.upstream_url ?? ""}
                autoComplete="off" {...aria("upstream_url")} onChange={(e) => set("upstream_url", e.target.value)} />
            </Field>
          ) : (
            <div className="space-y-3">
              {discoverErr && <p className="text-xs text-destructive">Could not list containers: {discoverErr}. Enter the name manually.</p>}
              <div className="grid gap-3 sm:grid-cols-2">
                <Field id="container" label="Container" error={err("container")}
                  hint={containers === null && loadContainers ? "Loading running containers..." : undefined}>
                  {containers && containers.length > 0 ? (
                    <select id="container" className={selectCls} value={f.container ?? ""} {...aria("container")}
                      onChange={(e) => pickContainer(e.target.value)}>
                      <option value="">Select a container...</option>
                      {f.container && !containers.some((c) => c.name === f.container) && <option value={f.container}>{f.container}</option>}
                      {containers.map((c) => <option key={c.name} value={c.name}>{c.name} {c.ports.length ? `(ports ${c.ports.join(", ")})` : "(no ports)"}</option>)}
                    </select>
                  ) : (
                    <Input id="container" value={f.container ?? ""} autoComplete="off" {...aria("container")}
                      onChange={(e) => set("container", e.target.value || null)} />
                  )}
                </Field>
                <Field id="cport" label="Container port" error={err("container_port")}>
                  <Input id="cport" type="number" min={1} max={65535} value={f.container_port ?? ""} {...aria("container_port")}
                    onChange={(e) => set("container_port", e.target.value ? Number(e.target.value) : null)} />
                  {ports.length > 1 && (
                    <div className="flex gap-1.5 pt-1">
                      {ports.map((p) => (
                        <Button key={p} type="button" size="xs" variant={p === f.container_port ? "default" : "outline"}
                          onClick={() => set("container_port", p)}>{p}</Button>
                      ))}
                    </div>
                  )}
                </Field>
              </div>
            </div>
          )}
          <Field id="health" label="Health path" error={err("health_path")} hint="Optional, e.g. /ping. Checked periodically.">
            <Input id="health" placeholder="/ping" value={f.health_path ?? ""} {...aria("health_path")}
              onChange={(e) => set("health_path", e.target.value || null)} />
          </Field>
          <SwitchRow id="verify-tls" label="Verify upstream TLS" hint="Turn off only for self-signed certificates on your LAN.">
            <Switch id="verify-tls" aria-label="Verify upstream TLS" checked={f.verify_tls} onCheckedChange={(v) => set("verify_tls", v)} />
          </SwitchRow>
          {!f.verify_tls && <RiskCallout title="TLS not verified">{RISK.tls}</RiskCallout>}
        </Section>

        <Section title="Access" hint="How the app is mounted and who can open it.">
          <div className="grid gap-3 sm:grid-cols-2">
            <Field id="mount" label="Mount mode">
              <select id="mount" className={selectCls} value={f.mount_mode}
                onChange={(e) => set("mount_mode", e.target.value as ProxiedServiceInput["mount_mode"])}>
                <option value="path">Path (/slug, app has base URL)</option>
                <option value="cookie-root">Cookie root (takeover)</option>
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
          {f.mount_mode === "cookie-root" && (
            <RiskCallout title="Takes over this browser" details={RISK_DETAIL.cookieRoot}>{RISK.cookieRoot}</RiskCallout>
          )}
          {f.auth_mode === "app-native" && <RiskCallout title="No Styx login">{RISK.appNative}</RiskCallout>}
          {f.auth_mode === "sso-with-bypass" && (
            <BypassRulesEditor rules={f.bypass_rules} errors={errors} onChange={(r) => set("bypass_rules", r)} />
          )}
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

        <Section title="Before you save">
          <RiskCallout title="Runs with your Styx rights" details={RISK_DETAIL.sameOrigin} footer={
            <label htmlFor="ack-origin" className="mt-2.5! flex items-start gap-2 rounded-md border border-border bg-background/60 p-2.5 text-sm text-foreground">
              <input id="ack-origin" type="checkbox" required checked={ack} onChange={(e) => setAck(e.target.checked)}
                className={`mt-0.5 ${checkCls}`} />
              <span>{ACK_TEXT}</span>
            </label>
          }>{RISK.sameOrigin}</RiskCallout>
        </Section>
        {stray.length > 0 && (
          <div role="alert" className="rounded-md border border-destructive/40 bg-destructive/5 p-2.5 text-xs text-destructive">
            {stray.map(([k, m]) => <p key={k}>{k}: {m}</p>)}
          </div>
        )}
      </DrawerBody>
      <DrawerFooter>
        {!ack && <p className="mr-auto self-center text-xs text-muted-foreground">Confirm the acknowledgement to save.</p>}
        <Button type="button" variant="ghost" onClick={onCancel}>Cancel</Button>
        <Button type="submit" disabled={!valid || !ack || saving} aria-busy={saving}>Save</Button>
      </DrawerFooter>
    </form>
  );
}
