import { useState } from "react";
import { ChevronDown, ChevronRight, ExternalLink } from "lucide-react";

const CF_DASH = "https://dash.cloudflare.com/";
const CF_TOKENS = "https://dash.cloudflare.com/profile/api-tokens";
const CF_PRICING = "https://developers.cloudflare.com/realtime/pricing/";

function Link({ href, children }: { href: string; children: React.ReactNode }) {
  return (
    <a href={href} target="_blank" rel="noreferrer" className="inline-flex items-center gap-0.5 underline">
      {children}
      <ExternalLink className="h-3 w-3" aria-hidden />
    </a>
  );
}

/** Step-by-step setup for the TURN relay, shown above the WebRTC / TURN settings. */
export function TurnSetupGuide({ provider }: { provider: unknown }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="mb-4 rounded-md border border-border bg-muted/30 p-3 text-sm">
      <button
        type="button"
        className="flex items-center gap-1 font-medium"
        aria-expanded={open}
        onClick={() => setOpen(!open)}
      >
        {open ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
        How to set up WebRTC and a TURN relay
      </button>
      {open && (
        <div className="mt-3 space-y-3 text-muted-foreground">
          <p>
            WebRTC streams with lower latency than WebSockets. Browsers on networks that block
            peer-to-peer UDP (most corporate networks) can only connect through a TURN relay.
            Without one, those viewers should stay on WebSockets.
          </p>
          {provider !== "generic" && (
            <div>
              <p className="font-medium text-foreground">Cloudflare Realtime TURN</p>
              <ol className="ml-5 list-decimal space-y-1">
                <li>
                  In the <Link href={CF_DASH}>Cloudflare dashboard</Link>, open <b>Realtime → TURN Server</b> and
                  select <b>Create</b>. Name it, e.g. <i>Styx-Portal</i>.
                </li>
                <li>
                  Copy the <b>Turn Token ID</b> and the <b>API Token</b> into the two Cloudflare TURN fields below.
                  The API token is shown only once.
                </li>
                <li>Set <b>TURN provider</b> to <i>cloudflare</i> and save.</li>
                <li>
                  Set <b>Default stream transport</b> to <i>webrtc</i>, or pick WebRTC per workstation under its
                  Stream settings.
                </li>
                <li>
                  Optional, for actual usage and a budget based on Cloudflare&apos;s figures: create an{" "}
                  <Link href={CF_TOKENS}>API token</Link> (<b>Create Token → Create Custom Token</b>), permission{" "}
                  <b>Account → Account Analytics → Read</b>, scoped to your account. Paste it with your{" "}
                  <b>Account ID</b> (dashboard search <kbd>Ctrl/Cmd+K</kbd> → &quot;Copy account ID&quot;).
                </li>
              </ol>
              <p className="mt-2">
                Cost: $0.05/GB relayed, the first 1,000 GB each month free (
                <Link href={CF_PRICING}>pricing</Link>). A 30 Mbps stream relays about 13 GB/hour.{" "}
                <b>TURN budget</b> switches everyone back to WebSockets when it is reached.
              </p>
            </div>
          )}
          {provider !== "cloudflare" && (
            <div>
              <p className="font-medium text-foreground">Your own TURN server (e.g. coturn)</p>
              <ol className="ml-5 list-decimal space-y-1">
                <li>
                  Run coturn on a host reachable by browsers and workstations. Open 3478/udp+tcp, and the relay
                  port range (default 49152–65535/udp).
                </li>
                <li>
                  In <code>turnserver.conf</code> set <code>use-auth-secret</code> and{" "}
                  <code>static-auth-secret=&lt;long random&gt;</code>. Optionally add TLS on 5349 or 443 with{" "}
                  <code>cert</code>/<code>pkey</code>.
                </li>
                <li>
                  Set <b>TURN provider</b> to <i>generic</i>, then fill in host, port, protocol (udp unless UDP is
                  blocked), TLS, and the <b>shared secret</b>. Use a username and password only for a fixed{" "}
                  <code>user=</code> entry.
                </li>
                <li>Choose WebRTC as the default transport or per workstation.</li>
              </ol>
            </div>
          )}
          <p>
            Check a connection: open <code>chrome://webrtc-internals</code> while streaming. A selected candidate
            pair of type <i>relay</i> means the TURN relay is in use (and billed); <i>host</i>/<i>srflx</i> means
            the connection is direct and free.
          </p>
        </div>
      )}
    </div>
  );
}
