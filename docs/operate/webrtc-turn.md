# WebRTC and TURN relays

Stream workstations over **WebRTC** for lower latency. Use a **TURN relay** so that
viewers on restrictive networks can still connect. Cost guards keep a paid relay
inside its free tier.

!!! info "Requires"
    Styx Portal 2.11+ and workstation agent 0.9.30+. All settings live in
    **Admin → Settings → WebRTC / TURN**; the in-app guide in that card repeats these steps.

## When to use it

| Transport | How video travels | Best for |
|---|---|---|
| **WebSockets** (default) | TCP, through the portal and its tunnel | Works everywhere, simplest |
| **WebRTC** | UDP, peer-to-peer, or via a TURN relay | Gaming and interactive work; about half the latency on a LAN |

Measured on a LAN with an RTX 4090 seat, input-to-screen p95 was 42 / 45 / 33 ms
(key / click / motion) over WebRTC, against 113 / 59 / 98 ms over WebSockets.

![WebRTC connection paths: signaling via the portal, direct UDP on open networks, or UDP via a TURN relay](../assets/diagrams/operate-webrtc-turn-1-light.svg#only-light)
![WebRTC connection paths: signaling via the portal, direct UDP on open networks, or UDP via a TURN relay](../assets/diagrams/operate-webrtc-turn-1-dark.svg#only-dark)

!!! warning "Corporate networks"
    Many corporate firewalls let UDP out to STUN servers but drop peer-to-peer replies.
    A direct WebRTC connection then never completes. Only a TURN relay works from such
    a network.

## Option A — Cloudflare Realtime TURN (managed)

1. In the [Cloudflare dashboard](https://dash.cloudflare.com/), open
   **Realtime → TURN Server** and select **Create**. Give it a name such as `Styx-Portal`.
2. Copy the **Turn Token ID** and the **API Token** shown after creation.

    !!! danger "The API token is shown once"
        Copy it straight into Styx. Treat it like a password. If it leaks (for example by
        being pasted into a chat), delete the key in Cloudflare and create a new one.

3. In Styx, open **Admin → Settings → WebRTC / TURN**:
    - **TURN provider** → `cloudflare`
    - **Cloudflare TURN token ID** → the Turn Token ID
    - **Cloudflare TURN API token** → the API Token (stored encrypted, never shown again)
4. Choose where WebRTC applies. Set **Default stream transport** to `webrtc`, or
   pick it for one workstation under its **Stream settings → Transport**.

### Optional: actual usage from Cloudflare

With an analytics token, the cost card shows Cloudflare's own egress figure. The
budget guard then uses that figure instead of Styx's metered estimate.

1. In **My Profile → API Tokens**, select **Create Token → Create Custom Token**.
2. Permission: **Account → Account Analytics → Read**. Account resources: your account.
   Create the token and copy it; it is shown once.
3. Find your **Account ID**: in the dashboard press **Ctrl/Cmd + K**, search
   *Copy account ID*, or look under **Workers & Pages → Account Details**.
4. In Styx set **Cloudflare account ID** and **Cloudflare analytics token**.

### Cost and the budget guard

Cloudflare bills **$0.05 per GB** sent from its relay to clients. The **first 1,000 GB
each month are free**, shared with the Realtime SFU
([pricing](https://developers.cloudflare.com/realtime/pricing/)). Only relayed
connections cost anything: direct WebRTC is free.

| Stream bitrate | GB per hour | Free hours per month |
|---|---|---|
| 15 Mbps | ≈ 6.8 | ≈ 150 |
| 30 Mbps | ≈ 13.5 | ≈ 75 |

Three guards keep the cost bounded:

- **TURN budget (GB / month)**, default 900. Once the month's relayed total reaches it,
  every workstation uses WebSockets until next month or until you raise it. The cost
  card shows a *WebRTC paused* banner. Sessions already running finish first.
- **Idle cutoff.** WebRTC sessions end after the workstation idle timeout with no
  input. A closed, hidden or crashed tab sends no activity, so it is cut too.
- **WebRTC max session (h)**, default 8. A hard cap on any single session.

![TURN budget decision: choose the usage source, compare to the budget, then hand out TURN or WebSockets](../assets/diagrams/operate-webrtc-turn-2-light.svg#only-light)
![TURN budget decision: choose the usage source, compare to the budget, then hand out TURN or WebSockets](../assets/diagrams/operate-webrtc-turn-2-dark.svg#only-dark)

## Option B — your own TURN server (coturn)

1. Run [coturn](https://github.com/coturn/coturn) on a host that both browsers and
   workstations can reach. Open **3478/udp+tcp** and the relay range (default
   **49152–65535/udp**). For TLS, also open **5349/tcp** (or 443).
2. In `turnserver.conf`:

    ```ini
    use-auth-secret
    static-auth-secret=<long random string>
    realm=turn.example.com
    # optional TLS
    cert=/etc/ssl/turn.pem
    pkey=/etc/ssl/turn.key
    ```

3. In Styx set **TURN provider** → `generic`, then **TURN host**, **TURN port** (3478, or
   5349/443 with TLS), **TURN protocol** (`udp` unless UDP is blocked), **TURN over TLS**,
   and **TURN shared secret** = the `static-auth-secret`. Use **TURN username/password**
   only with a fixed `user=name:password` entry. Shared-secret credentials are short-lived
   and preferred.

!!! note "No relay configured"
    With provider `none`, WebRTC uses direct and STUN connections only. Styx deliberately
    blanks the public demo relay that Selkies would otherwise fall back to.

## Verify a connection

1. Open `chrome://webrtc-internals` in another tab, then open the workstation.
2. Find the `candidate-pair` with state **succeeded**:
    - `relay` (local or remote) — traffic goes through TURN and counts against the budget.
    - `host` / `srflx` — direct, free.
3. Under `inbound-rtp (kind=video)`, `decoderImplementation` tells you whether the
   browser decodes in hardware. If it doesn't, pick a codec the viewer's GPU decodes. For
   example, choose HEVC for GPUs without AV1 decode, under the workstation's
   **Stream settings → Codec**.

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Spinner, no video; all candidate pairs stay *in-progress* | Peer-to-peer UDP blocked, no TURN | Configure a TURN provider |
| `onicecandidateerror` on TURN URLs | Wrong or expired TURN credentials | Re-create the Cloudflare key / check the coturn secret |
| WebRTC worked, now WebSockets everywhere | Budget reached | See the cost card; raise **TURN budget** or wait for next month |
| Picture letterboxed after going fullscreen | Older agent without WebRTC refit | Update the workstation agent to 0.9.30+ |
