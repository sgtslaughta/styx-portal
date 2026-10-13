import { AlertTriangle } from "lucide-react";
import { useId, useState, type ReactNode } from "react";
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
    "Mobile apps cannot use this mode.",
  sameOrigin:
    "Proxied apps share Styx's origin: scripts inside the app run in your browser with your Styx rights. " +
    "Only add apps you trust.",
  nativeApps:
    "Jellyfin's own login is exposed to the internet. Requests from its apps skip Styx login; rate limits and bans still apply.",
  passIdentity:
    "The app receives the signed-in user's name, email and groups. Only turn this on for apps that use them to sign people in.",
} as const;

/** Secondary context, collapsed behind "Details". */
export const RISK_DETAIL = {
  cookieRoot: "To leave, open /_styx/exit.",
  sameOrigin:
    "Styx no longer sends its API session to the app's server, but the app's scripts can still call Styx " +
    "as you. Admins should use a non-admin account for everyday use.",
} as const;

const DOCS = "/docs/SERVICES/#security-model";
const linkCls =
  "rounded-sm text-muted-foreground underline underline-offset-2 hover:text-foreground " +
  "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring";

export function RiskCallout({ title, children, details, footer, tone = "danger", className }: {
  /** Short scannable label, e.g. "No Styx login". */
  title?: string;
  /** The mandated risk text: always visible. */
  children: ReactNode;
  /** Optional secondary text, collapsed behind "Details". */
  details?: ReactNode;
  /** Extra content under the text (e.g. an acknowledgement checkbox). */
  footer?: ReactNode;
  tone?: "danger" | "warning";
  className?: string;
}) {
  const [open, setOpen] = useState(false);
  const detailsId = useId();
  const danger = tone === "danger";
  return (
    <div
      role="alert"
      className={cn(
        "flex gap-2.5 rounded-md border border-l-[3px] px-3 py-2.5 text-xs leading-relaxed text-foreground",
        danger
          ? "border-destructive/25 border-l-destructive bg-destructive/[0.06] dark:bg-destructive/10"
          : "border-warning/30 border-l-warning bg-warning/[0.07] dark:bg-warning/10",
        className,
      )}
    >
      <AlertTriangle className={cn("mt-px h-4 w-4 shrink-0", danger ? "text-destructive" : "text-warning")} aria-hidden />
      <div className="min-w-0 flex-1 space-y-1">
        <div className="flex flex-wrap items-baseline justify-between gap-x-3">
          {title && <p className="text-[13px] font-semibold leading-snug">{title}</p>}
          <div className="ml-auto flex gap-x-3">
            {details && (
              <button type="button" className={linkCls} aria-expanded={open} aria-controls={detailsId}
                onClick={() => setOpen((o) => !o)}>{open ? "Hide details" : "Details"}</button>
            )}
            <a className={linkCls} href={DOCS} target="_blank" rel="noreferrer">
              Learn more<span className="sr-only"> (opens in a new tab)</span>
            </a>
          </div>
        </div>
        <p className="text-foreground/85">{children}</p>
        {details && open && <p id={detailsId} className="text-muted-foreground">{details}</p>}
        {footer}
      </div>
    </div>
  );
}
