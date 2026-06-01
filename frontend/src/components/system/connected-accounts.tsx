import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/api/client";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Link as LinkIcon } from "lucide-react";

export function ConnectedAccounts() {
  const qc = useQueryClient();
  const { data: linked = [] } = useQuery({
    queryKey: ["linked-providers"],
    queryFn: api.linkedProviders,
  });
  const { data: providers = [] } = useQuery({
    queryKey: ["public-providers"],
    queryFn: api.oauthProviders,
  });

  const unlink = useMutation({
    mutationFn: (name: string) => api.unlinkProvider(name),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["linked-providers"] }),
  });

  const linkedNames = new Set(linked.map((l) => l.provider));
  const availableProviders = providers.filter((p) => !linkedNames.has(p.name));

  return (
    <Card>
      <CardHeader className="pb-4">
        <div className="flex items-center gap-3">
          <div className="rounded-lg bg-primary/10 p-2">
            <LinkIcon className="h-5 w-5 text-primary" />
          </div>
          <div>
            <CardTitle>Connected accounts</CardTitle>
            <CardDescription>Link external identity providers to your account</CardDescription>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {linked.length > 0 && (
          <div className="border border-border rounded-lg overflow-hidden">
            <table className="w-full text-sm">
              <thead className="border-b border-border bg-muted/40">
                <tr>
                  <th className="px-4 py-3 text-left font-semibold text-sm">Provider</th>
                  <th className="px-4 py-3 text-left font-semibold text-sm">Email</th>
                  <th className="px-4 py-3 text-right font-semibold text-sm">Actions</th>
                </tr>
              </thead>
              <tbody>
                {linked.map((l) => (
                  <tr key={l.provider} className="border-b border-border hover:bg-muted/30 transition-colors">
                    <td className="px-4 py-3 font-medium capitalize">{l.provider}</td>
                    <td className="px-4 py-3 text-muted-foreground">
                      {l.email || "—"}
                    </td>
                    <td className="px-4 py-3 text-right">
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => unlink.mutate(l.provider)}
                        disabled={unlink.isPending}
                        className="text-destructive hover:text-destructive hover:bg-destructive/10"
                      >
                        Unlink
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {availableProviders.length > 0 && (
          <div className="space-y-2">
            <div className="text-sm font-medium text-muted-foreground">
              {linked.length > 0 ? "Link additional account" : "No linked accounts yet"}
            </div>
            <div className="grid gap-2">
              {availableProviders.map((p) => (
                <a
                  key={p.name}
                  href={api.linkStartUrl(p.name)}
                  className="block rounded-md border border-border bg-background px-4 py-3 text-sm font-medium hover:bg-muted transition-colors"
                >
                  Link {p.display_label}
                </a>
              ))}
            </div>
          </div>
        )}

        {linked.length === 0 && availableProviders.length === 0 && (
          <div className="text-center py-8">
            <LinkIcon className="h-8 w-8 text-muted-foreground/40 mx-auto mb-2" />
            <div className="text-sm text-muted-foreground">
              No identity providers available
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
