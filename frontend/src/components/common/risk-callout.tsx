import { AlertTriangle } from "lucide-react";
import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

/** Exact security wording from the service-proxy spec section 9. Do not soften. */
export const RISK = {
  bypass: (prefix: string) =>
    `Requests matching ${prefix} are reachable from the internet WITHOUT Styx login. ` +
    "Only the app's own credential and rate limiting protect them.",
  appNative: "Styx does not authenticate this service. The app must enforce its own login.",
  tls: "Upstream certificate is not verified. Traffic between Styx and this host can be intercepted on your LAN.",
  cookieRoot:
    "Takes over the root of the hostname for this browser. One service at a time. " +
    "Mobile apps cannot use this mode. To leave, open /_styx/exit.",
  sameOrigin:
    "Proxied apps share Styx's origin. Styx no longer sends its API session to the app's server, " +
    "but scripts inside the app run in your browser with your Styx rights. Only add apps you trust; " +
    "admins should use a non-admin account for everyday use.",
} as const;

export function RiskCallout({ children, tone = "danger" }: { children: ReactNode; tone?: "danger" | "warning" }) {
  const danger = tone === "danger";
  return (
    <div
      role="alert"
      className={cn(
        "flex gap-2.5 rounded-md border p-2.5 text-xs leading-relaxed text-foreground",
        danger ? "border-destructive/50 bg-destructive/10" : "border-warning/50 bg-warning/10",
      )}
    >
      <AlertTriangle className={cn("mt-0.5 h-4 w-4 shrink-0", danger ? "text-destructive" : "text-warning")} aria-hidden />
      <div>
        <span>{children}</span>{" "}
        <a className="whitespace-nowrap underline underline-offset-2" href="/docs/SERVICES/#security-model"
           target="_blank" rel="noreferrer">Learn more</a>
      </div>
    </div>
  );
}
