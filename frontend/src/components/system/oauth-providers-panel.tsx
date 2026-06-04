import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, type OAuthProviderCreate } from "@/api/client";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Shield } from "lucide-react";

const EMPTY: OAuthProviderCreate = {
  name: "",
  display_label: "",
  kind: "oidc",
  issuer_url: "",
  client_id: "",
  client_secret: "",
  scopes: "openid email profile",
};

export function OAuthProvidersPanel() {
  const qc = useQueryClient();
  const { data: providers = [] } = useQuery({
    queryKey: ["oauth-providers"],
    queryFn: api.listOAuthProviders,
  });
  const [form, setForm] = useState<OAuthProviderCreate>(EMPTY);

  const create = useMutation({
    mutationFn: () => api.createOAuthProvider(form),
    onSuccess: () => {
      setForm(EMPTY);
      qc.invalidateQueries({ queryKey: ["oauth-providers"] });
    },
  });

  const toggle = useMutation({
    mutationFn: (p: { id: string; enabled: boolean }) =>
      api.updateOAuthProvider(p.id, { enabled: p.enabled }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["oauth-providers"] }),
  });

  const remove = useMutation({
    mutationFn: (id: string) => api.deleteOAuthProvider(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["oauth-providers"] }),
  });

  const set = (k: keyof OAuthProviderCreate) => (
    e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>
  ) => setForm({ ...form, [k]: e.target.value });

  return (
    <div className="space-y-6">
      <Card className="styx-card">
        <CardHeader className="pb-4">
          <div className="flex items-center gap-3">
            <div className="rounded-lg bg-primary/10 p-2">
              <Shield className="h-5 w-5 text-primary" />
            </div>
            <div>
              <CardTitle>OAuth / SSO providers</CardTitle>
              <CardDescription>Configure identity providers for federated authentication</CardDescription>
            </div>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          {providers.length > 0 && (
            <div className="border border-border rounded-lg overflow-hidden">
              <table className="w-full text-sm">
                <thead className="border-b border-border bg-muted/40">
                  <tr>
                    <th className="px-4 py-3 text-left font-semibold text-sm">Name</th>
                    <th className="px-4 py-3 text-left font-semibold text-sm">Kind</th>
                    <th className="px-4 py-3 text-left font-semibold text-sm">Enabled</th>
                    <th className="px-4 py-3 text-left font-semibold text-sm">Secret</th>
                    <th className="px-4 py-3 text-right font-semibold text-sm">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {providers.map((p) => (
                    <tr key={p.id} className="border-b border-border hover:bg-muted/30 transition-colors">
                      <td className="px-4 py-3 font-medium">
                        {p.display_label}{" "}
                        <span className="text-muted-foreground">({p.name})</span>
                      </td>
                      <td className="px-4 py-3">
                        <span className="inline-flex items-center rounded-full bg-secondary/10 px-2.5 py-1 text-xs font-medium text-secondary-foreground">
                          {p.kind}
                        </span>
                      </td>
                      <td className="px-4 py-3">
                        <input
                          type="checkbox"
                          checked={p.enabled}
                          onChange={(e) =>
                            toggle.mutate({ id: p.id, enabled: e.target.checked })
                          }
                          className="h-4 w-4 rounded cursor-pointer"
                        />
                      </td>
                      <td className="px-4 py-3 text-xs text-muted-foreground">
                        {p.has_secret ? (
                          <span className="inline-flex items-center rounded-full bg-success/10 px-2.5 py-1 text-xs font-medium text-success">
                            set
                          </span>
                        ) : (
                          <span className="inline-flex items-center rounded-full bg-muted px-2.5 py-1 text-xs font-medium text-muted-foreground">
                            unset
                          </span>
                        )}
                      </td>
                      <td className="px-4 py-3 text-right">
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => remove.mutate(p.id)}
                          disabled={remove.isPending}
                          className="text-destructive hover:text-destructive hover:bg-destructive/10"
                        >
                          Delete
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          <div className="rounded-lg border border-border bg-muted/40 p-4 space-y-3">
            <div className="font-semibold text-sm">Add new provider</div>
            <Input
              placeholder="name (e.g. authentik, github)"
              value={form.name}
              onChange={set("name")}
            />
            <Input
              placeholder="display label (e.g. My Authentik)"
              value={form.display_label}
              onChange={set("display_label")}
            />
            <select
              className="w-full rounded-md border border-border bg-background p-2 text-sm"
              value={form.kind}
              onChange={set("kind")}
            >
              <option value="oidc">OIDC (generic / Google / Authentik)</option>
              <option value="oauth2">OAuth2 (GitHub)</option>
            </select>
            <Input
              placeholder="issuer url (OIDC discovery base; leave blank for github)"
              value={form.issuer_url || ""}
              onChange={set("issuer_url")}
            />
            <Input
              placeholder="client id"
              value={form.client_id}
              onChange={set("client_id")}
            />
            <Input
              type="password"
              placeholder="client secret"
              value={form.client_secret}
              onChange={set("client_secret")}
            />
            <Input
              placeholder="scopes (space-separated)"
              value={form.scopes || ""}
              onChange={set("scopes")}
            />
            <Button
              onClick={() => create.mutate()}
              disabled={create.isPending}
              className="w-full"
            >
              {create.isPending ? "Adding..." : "Add provider"}
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
