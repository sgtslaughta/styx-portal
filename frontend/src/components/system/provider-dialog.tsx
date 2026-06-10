import { useEffect, useRef, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  api, type OAuthProviderRow, type OAuthProviderCreate, type ProviderTestResult,
} from "@/api/client";
import { KeyRound, Upload, X, Check, AlertCircle, ChevronDown, Link2, Copy } from "lucide-react";

const MAX_ICON_BYTES = 200 * 1024;

const EMPTY: OAuthProviderCreate = {
  name: "", display_label: "", kind: "oidc", issuer_url: "",
  client_id: "", client_secret: "", scopes: "openid email profile",
  icon_url: null, trust_email: false, allow_signup: false,
};

type RoleMap = { claim?: string; user_group?: string; admin_group?: string };

type Props = {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  editing: OAuthProviderRow | null;
};

export function ProviderDialog({ open, onOpenChange, editing }: Props) {
  const qc = useQueryClient();
  const [form, setForm] = useState<OAuthProviderCreate>(EMPTY);
  const [advanced, setAdvanced] = useState(false);
  const [test, setTest] = useState<ProviderTestResult | null>(null);
  const [probe, setProbe] = useState<Record<string, unknown> | null>(null);
  const [groupsClaim, setGroupsClaim] = useState("groups");
  const [userGroup, setUserGroup] = useState("");
  const [adminGroup, setAdminGroup] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!open) return;
    setTest(null);
    setProbe(null);
    if (editing) {
      setForm({
        name: editing.name,
        display_label: editing.display_label,
        kind: editing.kind,
        issuer_url: editing.issuer_url ?? "",
        client_id: editing.client_id,
        client_secret: "",
        scopes: editing.scopes,
        icon_url: editing.icon_url,
        trust_email: editing.trust_email,
        allow_signup: editing.allow_signup,
      });
      const rm = (editing.role_map ?? {}) as RoleMap;
      setGroupsClaim(rm.claim || "groups");
      setUserGroup(rm.user_group || "");
      setAdminGroup(rm.admin_group || "");
    } else {
      setForm(EMPTY);
      setGroupsClaim("groups");
      setUserGroup("");
      setAdminGroup("");
    }
  }, [open, editing]);

  function buildRoleMap(): RoleMap {
    const rm: RoleMap = { claim: groupsClaim.trim() || "groups" };
    if (userGroup.trim()) rm.user_group = userGroup.trim();
    if (adminGroup.trim()) rm.admin_group = adminGroup.trim();
    return rm;
  }

  const set = (k: keyof OAuthProviderCreate) => (
    e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>
  ) => setForm((f) => ({ ...f, [k]: e.target.value }));

  function autoName(label: string) {
    if (editing) return;
    const slug = label.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
    setForm((f) => ({ ...f, display_label: label, name: slug }));
  }

  function onPickIcon(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    if (file.size > MAX_ICON_BYTES) {
      toast.error("Icon too large (max 200KB)");
      return;
    }
    const reader = new FileReader();
    reader.onload = () => setForm((f) => ({ ...f, icon_url: String(reader.result) }));
    reader.readAsDataURL(file);
  }

  const save = useMutation({
    mutationFn: () => {
      if (editing) {
        const patch: Partial<OAuthProviderCreate> & { enabled?: boolean } = {
          display_label: form.display_label,
          issuer_url: form.issuer_url,
          client_id: form.client_id,
          scopes: form.scopes,
          icon_url: form.icon_url,
          trust_email: form.trust_email,
          allow_signup: form.allow_signup,
          role_map: buildRoleMap(),
          authorize_url: form.authorize_url,
          token_url: form.token_url,
          userinfo_url: form.userinfo_url,
        };
        if (form.client_secret) patch.client_secret = form.client_secret;
        return api.updateOAuthProvider(editing.id, patch);
      }
      return api.createOAuthProvider({ ...form, role_map: buildRoleMap() });
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["oauth-providers"] });
      toast.success(editing ? "Provider updated" : "Provider added");
      onOpenChange(false);
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const checkConfig = useMutation({
    mutationFn: () => api.testOAuthConfig(editing!.id),
    onSuccess: (r) => setTest(r),
    onError: (e: Error) => toast.error(e.message),
  });

  function testLogin() {
    if (!editing) return;
    const w = window.open(api.oauthTestStartUrl(editing.id), "sso-test",
      "width=520,height=640");
    const onMsg = (ev: MessageEvent) => {
      if (ev.origin !== window.location.origin) return;
      if (ev.data?.type === "sso-test") {
        setProbe(ev.data.result);
        window.removeEventListener("message", onMsg);
        w?.close();
      }
    };
    window.addEventListener("message", onMsg);
  }

  const canSave = form.display_label && form.name && form.client_id &&
    (editing || form.client_secret) &&
    (form.kind !== "oidc" || form.issuer_url);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex max-h-[90vh] max-w-2xl flex-col">
        <DialogHeader>
          <DialogTitle>{editing ? "Edit provider" : "Add SSO provider"}</DialogTitle>
          <DialogDescription>
            Connect an identity provider so users can sign in with single sign-on.
          </DialogDescription>
        </DialogHeader>

        <div className="-mr-2 flex-1 space-y-3 overflow-y-auto pr-2">
          {/* BASIC SECTION — always visible */}
          <Field label="Display name" hint="Shown to users on the login button.">
            <Input
              autoFocus
              value={form.display_label}
              onChange={(e) => autoName(e.target.value)}
              placeholder="My Authentik"
            />
          </Field>

          <Field label="Internal name" hint="Lowercase id used in URLs. Locked after creation.">
            <Input
              value={form.name}
              onChange={set("name")}
              disabled={!!editing}
              placeholder="authentik"
            />
          </Field>

          <Field label="Type">
            <select
              className="w-full rounded-md border border-border bg-background p-2 text-sm"
              value={form.kind}
              onChange={set("kind")}
              disabled={!!editing}
            >
              <option value="oidc">OIDC — Authentik, Google, Keycloak, generic</option>
              <option value="oauth2">OAuth2 — GitHub</option>
            </select>
          </Field>

          <Field label="Client ID">
            <Input value={form.client_id} onChange={set("client_id")} />
          </Field>

          <Field
            label="Client secret"
            hint={editing ? "Leave blank to keep the current secret." : undefined}
          >
            <Input
              type="password"
              value={form.client_secret}
              onChange={set("client_secret")}
              placeholder={editing ? "•••• unchanged" : ""}
            />
          </Field>

          <Field label="Icon" hint="URL or upload. Shown on the login button.">
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-md border border-border bg-muted/40 overflow-hidden">
                {form.icon_url ? (
                  <img src={form.icon_url} alt="" className="h-6 w-6 object-contain" />
                ) : (
                  <KeyRound className="h-4 w-4 text-muted-foreground" />
                )}
              </div>
              <Input
                value={form.icon_url ?? ""}
                placeholder="https://…/logo.svg"
                onChange={(e) =>
                  setForm((f) => ({ ...f, icon_url: e.target.value || null }))
                }
              />
              <input
                ref={fileRef}
                type="file"
                accept="image/*"
                hidden
                onChange={onPickIcon}
              />
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => fileRef.current?.click()}
                aria-label="Upload icon"
              >
                <Upload className="h-4 w-4" />
              </Button>
              {form.icon_url && (
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={() => setForm((f) => ({ ...f, icon_url: null }))}
                  aria-label="Clear icon"
                >
                  <X className="h-4 w-4" />
                </Button>
              )}
            </div>
          </Field>

          {/* ENDPOINTS SECTION — collapsible, open by default for oauth2 */}
          <details
            className="rounded-md border border-border"
            open={form.kind === "oauth2"}
          >
            <summary className="cursor-pointer select-none px-3 py-2 text-sm font-medium hover:bg-muted/40 transition-colors">
              Endpoints
            </summary>
            <div className="space-y-3 px-3 pb-3">
              {form.kind === "oidc" && (
                <Field label="Issuer URL" hint="We auto-discover endpoints from here.">
                  <Input
                    value={form.issuer_url || ""}
                    onChange={set("issuer_url")}
                    placeholder="https://auth.example.com/application/o/styx/"
                  />
                </Field>
              )}

              <div className="space-y-2 rounded-md border border-border bg-muted/30 p-3">
                <div className="flex items-center gap-1.5 text-xs font-medium">
                  <Link2 className="h-3.5 w-3.5 text-muted-foreground" />
                  Redirect URI — register this in your identity provider
                </div>
                <CopyRow
                  label="Login callback"
                  value={
                    editing
                      ? editing.redirect_uri
                      : `${window.location.origin}/api/auth/oauth/${form.name || "your-provider"}/callback`
                  }
                />
                {editing ? (
                  <CopyRow label="Test-login callback" value={editing.test_redirect_uri} />
                ) : (
                  <p className="text-[11px] text-muted-foreground">
                    Save the provider to get its Test-login callback URL.
                  </p>
                )}
                <p className="text-[11px] text-muted-foreground">
                  Must match exactly — scheme, host, path, and case. Use Strict matching in your IdP.
                </p>
              </div>

              <Field label="Scopes">
                <Input value={form.scopes || ""} onChange={set("scopes")} />
              </Field>

              <button
                type="button"
                onClick={() => setAdvanced((v) => !v)}
                className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors"
              >
                <ChevronDown
                  className={`h-3 w-3 transition-transform ${advanced ? "rotate-180" : ""}`}
                />
                Advanced — manual endpoint overrides
              </button>

              {advanced && (
                <div className="space-y-2 rounded-md border border-border p-3">
                  <Input
                    placeholder="authorize_url"
                    value={form.authorize_url || ""}
                    onChange={set("authorize_url")}
                  />
                  <Input
                    placeholder="token_url"
                    value={form.token_url || ""}
                    onChange={set("token_url")}
                  />
                  <Input
                    placeholder="userinfo_url"
                    value={form.userinfo_url || ""}
                    onChange={set("userinfo_url")}
                  />
                </div>
              )}
            </div>
          </details>

          {/* ROLE MAPPING SECTION — collapsible, closed by default */}
          <details className="rounded-md border border-border">
            <summary className="cursor-pointer select-none px-3 py-2 text-sm font-medium hover:bg-muted/40 transition-colors">
              Role mapping
            </summary>
            <div className="space-y-3 px-3 pb-3">
              <div className="grid grid-cols-3 gap-2">
                <Field label="Groups claim" hint="Userinfo claim holding the user's groups.">
                  <Input
                    value={groupsClaim}
                    onChange={(e) => setGroupsClaim(e.target.value)}
                    placeholder="groups"
                  />
                </Field>
                <Field label="User group" hint="Required to sign up (blank = anyone).">
                  <Input
                    value={userGroup}
                    onChange={(e) => setUserGroup(e.target.value)}
                    placeholder="styx-users"
                  />
                </Field>
                <Field label="Admin group" hint="Members get the admin role.">
                  <Input
                    value={adminGroup}
                    onChange={(e) => setAdminGroup(e.target.value)}
                    placeholder="styx-admins"
                  />
                </Field>
              </div>
              <p className="text-[11px] text-muted-foreground">
                Admin group → admin. With a user group set, only its members may sign up; leave it
                blank to allow anyone the provider authenticates. Group mapping also applies to
                invited users.
              </p>
            </div>
          </details>

          {/* SELF-SERVICE SECTION — collapsible, closed by default */}
          <details className="rounded-md border border-border">
            <summary className="cursor-pointer select-none px-3 py-2 text-sm font-medium hover:bg-muted/40 transition-colors">
              Self-service
            </summary>
            <div className="space-y-3 px-3 pb-3">
              <label className="flex items-start gap-3 rounded-md border border-border p-3 cursor-pointer hover:bg-muted/20 transition-colors">
                <input
                  type="checkbox"
                  checked={!!form.trust_email}
                  className="mt-0.5 h-4 w-4"
                  onChange={(e) =>
                    setForm((f) => ({ ...f, trust_email: e.target.checked }))
                  }
                />
                <span className="text-sm">
                  <span className="font-medium">Trust emails from this provider</span>
                  <span className="block text-xs text-muted-foreground">
                    Enable if your IdP (e.g. Authentik) doesn't send a verified-email claim.
                    Email is still required.
                  </span>
                </span>
              </label>

              <label className="flex items-start gap-3 cursor-pointer">
                <input
                  type="checkbox"
                  checked={!!form.allow_signup}
                  className="mt-0.5 h-4 w-4"
                  onChange={(e) =>
                    setForm((f) => ({ ...f, allow_signup: e.target.checked }))
                  }
                />
                <span className="text-sm">
                  <span className="font-medium">Allow new users to sign up</span>
                  <span className="block text-xs text-muted-foreground">
                    Auto-create accounts on first login without an invite. Otherwise sign-in
                    is invite-only.
                  </span>
                </span>
              </label>
            </div>
          </details>

          {editing && (
            <div className="flex gap-2">
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => checkConfig.mutate()}
                disabled={checkConfig.isPending}
              >
                {checkConfig.isPending ? "Checking…" : "Check config"}
              </Button>
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={testLogin}
              >
                Test login
              </Button>
            </div>
          )}

          {!editing && (
            <p className="text-xs text-muted-foreground">
              Save the provider to enable Check config / Test login.
            </p>
          )}

          {test && (
            <div className="space-y-1 rounded-md border border-border p-3 text-xs">
              {test.checks.map((c) => (
                <div key={c.label} className="flex items-center gap-2">
                  {c.ok ? (
                    <Check className="h-3 w-3 text-success" />
                  ) : (
                    <AlertCircle className="h-3 w-3 text-destructive" />
                  )}
                  <span className="font-medium">{c.label}</span>
                  <span className="text-muted-foreground truncate">{c.detail}</span>
                </div>
              ))}
            </div>
          )}

          {probe && (
            <div className="rounded-md border border-border p-3 text-xs">
              <div
                className={
                  probe.would_pass ? "text-success font-medium" : "text-destructive font-medium"
                }
              >
                {probe.would_pass
                  ? "✓ A real login would succeed"
                  : "✗ A real login would be rejected"}
              </div>
              <pre className="mt-2 max-h-40 overflow-auto whitespace-pre-wrap text-[10px] text-muted-foreground font-mono">
                {JSON.stringify(probe, null, 2)}
              </pre>
            </div>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            onClick={() => save.mutate()}
            disabled={!canSave || save.isPending}
          >
            {save.isPending ? "Saving…" : editing ? "Save changes" : "Add provider"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-1">
      <label className="block text-xs font-medium text-muted-foreground">{label}</label>
      {children}
      {hint && <p className="text-[11px] text-muted-foreground">{hint}</p>}
    </div>
  );
}

function CopyRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="space-y-0.5">
      <div className="text-[11px] text-muted-foreground">{label}</div>
      <div className="flex items-start gap-2">
        <code className="flex-1 break-all rounded border border-border bg-background px-2 py-1 font-mono text-[11px]">
          {value}
        </code>
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={() => {
            navigator.clipboard?.writeText(value);
            toast.success("Copied");
          }}
          aria-label="Copy to clipboard"
        >
          <Copy className="h-3.5 w-3.5" />
        </Button>
      </div>
    </div>
  );
}
