import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, type OAuthProviderRow } from "@/api/client";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Shield, Plus, KeyRound } from "lucide-react";
import { ProviderDialog } from "./provider-dialog";

export function OAuthProvidersPanel() {
  const qc = useQueryClient();
  const { data: providers = [] } = useQuery({
    queryKey: ["oauth-providers"],
    queryFn: api.listOAuthProviders,
  });
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editing, setEditing] = useState<OAuthProviderRow | null>(null);

  const toggle = useMutation({
    mutationFn: (p: { id: string; enabled: boolean }) =>
      api.updateOAuthProvider(p.id, { enabled: p.enabled }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["oauth-providers"] }),
  });
  const remove = useMutation({
    mutationFn: (id: string) => api.deleteOAuthProvider(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["oauth-providers"] }),
  });

  function openAdd() { setEditing(null); setDialogOpen(true); }
  function openEdit(p: OAuthProviderRow) { setEditing(p); setDialogOpen(true); }

  return (
    <div className="space-y-6">
      <Card className="styx-card">
        <CardHeader className="pb-4">
          <div className="flex items-center justify-between gap-3">
            <div className="flex items-center gap-3">
              <div className="rounded-lg bg-primary/10 p-2">
                <Shield className="h-5 w-5 text-primary" />
              </div>
              <div>
                <CardTitle>OAuth / SSO providers</CardTitle>
                <CardDescription>Configure identity providers for federated authentication</CardDescription>
              </div>
            </div>
            <Button onClick={openAdd} size="sm">
              <Plus className="h-4 w-4" /> Add provider
            </Button>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          {providers.length === 0 ? (
            <div className="rounded-lg border border-dashed border-border p-8 text-center text-sm text-muted-foreground">
              No providers yet. Click <span className="font-medium">Add provider</span> to connect Authentik, Google, GitHub, or any OIDC provider.
            </div>
          ) : (
            <div className="border border-border rounded-lg overflow-hidden">
              <table className="w-full text-sm">
                <thead className="border-b border-border bg-muted/40">
                  <tr>
                    <th className="px-4 py-3 text-left font-semibold">Provider</th>
                    <th className="px-4 py-3 text-left font-semibold">Kind</th>
                    <th className="px-4 py-3 text-left font-semibold">Enabled</th>
                    <th className="px-4 py-3 text-right font-semibold">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {providers.map((p) => (
                    <tr key={p.id} className="border-b border-border hover:bg-muted/30 transition-colors">
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-2.5 font-medium">
                          <span className="flex h-7 w-7 items-center justify-center rounded-md border border-border bg-muted/40 overflow-hidden">
                            {p.icon_url
                              ? <img src={p.icon_url} alt="" className="h-4 w-4 object-contain" />
                              : <KeyRound className="h-3.5 w-3.5 text-muted-foreground" />}
                          </span>
                          {p.display_label}{" "}
                          <span className="text-muted-foreground">({p.name})</span>
                        </div>
                      </td>
                      <td className="px-4 py-3">
                        <span className="inline-flex items-center rounded-full bg-secondary/10 px-2.5 py-1 text-xs font-medium text-secondary-foreground">
                          {p.kind}
                        </span>
                      </td>
                      <td className="px-4 py-3">
                        <input type="checkbox" checked={p.enabled}
                               onChange={(e) => toggle.mutate({ id: p.id, enabled: e.target.checked })}
                               className="h-4 w-4 rounded cursor-pointer" />
                      </td>
                      <td className="px-4 py-3 text-right">
                        <Button variant="ghost" size="sm" onClick={() => openEdit(p)}>Edit</Button>
                        <Button variant="ghost" size="sm" onClick={() => remove.mutate(p.id)}
                                disabled={remove.isPending}
                                className="text-destructive hover:text-destructive hover:bg-destructive/10">
                          Delete
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      <ProviderDialog open={dialogOpen} onOpenChange={setDialogOpen} editing={editing} />
    </div>
  );
}
