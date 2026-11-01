import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, CheckCircle2, Loader2, MinusCircle, XCircle } from "lucide-react";
import { api, type TurnCheckStatus } from "@/api/client";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

const ICON = {
  ok: { Icon: CheckCircle2, cls: "text-emerald-500", text: "OK" },
  warn: { Icon: AlertTriangle, cls: "text-amber-500", text: "Warning" },
  error: { Icon: XCircle, cls: "text-red-500", text: "Error" },
  skip: { Icon: MinusCircle, cls: "text-muted-foreground", text: "Skipped" },
} satisfies Record<TurnCheckStatus, { Icon: unknown; cls: string; text: string }>;

export function TurnSetupCheck({ provider }: { provider: string }) {
  const { data, isFetching, isError, refetch } = useQuery({
    queryKey: ["turn-check"],
    queryFn: () => api.getTurnCheck(),
    enabled: provider !== "none",
    retry: false,
    refetchOnWindowFocus: false,
    staleTime: Infinity,
  });

  return (
    <Card className="styx-card">
      <CardHeader className="pb-4">
        <div className="flex items-center justify-between gap-3">
          <CardTitle>Cloudflare / TURN status</CardTitle>
          <Button size="sm" variant="outline" disabled={isFetching} onClick={() => void refetch()}>
            {isFetching && <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden />}
            Check setup
          </Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        {isError && <p role="alert" className="text-sm text-red-500">Check failed. Try again.</p>}
        {!data && !isError && !isFetching && (
          <p className="text-sm text-muted-foreground">
            {provider === "none" ? "No TURN provider selected. " : ""}Press Check setup to verify.
          </p>
        )}
        {data && (
          <>
            <ul className="space-y-2">
              {data.checks.map((c) => {
                const { Icon, cls, text } = ICON[c.status];
                return (
                  <li key={c.id} className="flex items-start gap-2 text-sm">
                    <Icon className={`mt-0.5 h-4 w-4 shrink-0 ${cls}`} aria-hidden />
                    <div>
                      <span className="font-medium">{c.label}</span>{" "}
                      <span className={`text-xs font-semibold uppercase ${cls}`}>{text}</span>
                      <p className="text-muted-foreground">{c.detail}</p>
                    </div>
                  </li>
                );
              })}
            </ul>
            <p className="text-xs text-muted-foreground">
              Checked at {new Date(data.checked_at).toLocaleString()}
            </p>
          </>
        )}
      </CardContent>
    </Card>
  );
}
