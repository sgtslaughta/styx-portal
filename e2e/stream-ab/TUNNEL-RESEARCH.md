# Tunnel latency research (2026-10-31, read-only, not committed)

Evidence grade: A = vendor doc/source read, B = secondary/paraphrase, C = inference (mine).
Searches were shallow (6 fetches). No cloudflared GitHub issue directly on WS latency was found.

## Diagnosis first (C)
Your simulated tunnel was order-preserving, lossless, only +40 ms RTT, yet p95 went 72 -> 750-900 ms
and p99 to seconds. A 40 ms RTT alone cannot do that. The likely culprit is Selkies websockets
mode itself: per-client backpressure is driven by CLIENT_FRAME_ACK desync minus a smoothed RTT
allowance, and `congestion_control` (default true) uses "frame round-trip queuing and jitter" on
WebSockets (A: settings.py, docs.linuxserver.io protocol). Jitter 0-25 ms on a 60 fps stream
(16.7 ms/frame) = acks arrive in bursts -> server sees desync -> withholds frames/lowers bitrate ->
stalls + keyframe recovery. Plus plain TCP: a 30 Mbps stream in one TCP conn buffers in socket/proxy
send queues (bufferbloat) and any delay is added to every frame behind it. So the tunnel is
probably not the main lever; transport choice (UDP/WebRTC) and Selkies pacing are.
Cheap proof: run the same sim with `congestion_control=false` (see #1).

## Q1. cloudflared knobs (all small effect, A unless noted)
- protocol: default auto (QUIC, falls back to http2). You already use quic. Keep. Source:
  developers.cloudflare.com/cloudflare-one/connections/connect-networks/configure-tunnels/cloudflared-parameters/run-parameters/
- originRequest (same docs, .../origin-parameters/): connectTimeout 30s, tcpKeepAlive 30s,
  keepAliveConnections 100, keepAliveTimeout 1m30s, noHappyEyeballs false, http2Origin false,
  disableChunkedEncoding false, proxyType "" . None affect steady-state WS throughput/latency;
  they govern connection setup/pooling. No tunable QUIC window/flow-control flags are documented
  (searched; absent). noHappyEyeballs:true only saves ms at connect. http2Origin: leave false
  (WS upgrade over h1.1 is the normal path; h2 adds a mux layer to Traefik for no gain, C).
- edge-ip-version default 4; `auto` may give IPv6 edge path - try, measure RTT (C, low value).
- region: only `us` exists; irrelevant to ewr/phl. Don't set.
- post-quantum: QUIC uses PQ key agreement by default; only affects handshake, not data rate.
- compression: no cloudflared compression knob found. (Zone-level Brotli does not apply to WS frames, B.)
- Edge buffering / caps: docs state no per-connection bandwidth cap and give no idle timeout
  number for WS (page omits it; the commonly cited 100 s is for HTTP proxy read timeout, B).
  Doc: developers.cloudflare.com/network/websockets/ . Undocumented => weak evidence either way.
  Selkies sends constant traffic so idle timeout is moot.
- Structural (B): after upgrade the WS is an opaque byte pipe: client TCP <-> edge <-> QUIC stream
  <-> cloudflared <-> TCP to Traefik. Three TCP/QUIC loops in series, each with own congestion
  control and retransmit: loss on the browser-edge TCP leg causes HoL stalls (seconds at p99 are
  plausible with retransmit backoff). Not fixable by flags.
- Cloudflare 2025 change: UDP in cloudflared was re-architected (developers.cloudflare.com/changelog/2025-07-15-udp-improvements/)
  - only matters for UDP proxying (private-network/WARP), not HTTP/WS.
- Known QUIC CC bug (CUBIC cwnd stuck at min after collapse, Cloudflare quiche, 2026) -
  blog.cloudflare.com/quic-death-spiral-fix/ (B, only via secondary summaries; I did not read the
  primary). Could explain "intermittent stalls" on the cloudflared<->edge leg. Action: confirm
  cloudflared >= version that bundled the fix (release notes), you run 2026.10.7 (C).

## Q2. Zone / dashboard
- Network > WebSockets must be On (default on). A.
- Argo Smart Routing: Cloudflare WS page lists Argo as NOT compatible with WebSockets (A, network/websockets).
  Argo docs don't mention Tunnel. Skip / low expectation. Paid per GB.
- HTTP/3 to client: affects HTTP requests, not an established WS over TCP (WS-over-h3 not used by
  browsers for Selkies' wss://) (C). Leave on.
- 0-RTT, Rocket Loader, Polish, Auto-minify: irrelevant to WS frames, but turn off for the g.
  hostname to be safe (cheap config rule, C). Also bypass cache/WAF/Bot Fight for the host: WAF
  inspects only the 101 upgrade (A).
- Spectrum (TCP/UDP proxy): Enterprise-only for arbitrary ports (B, not verified - search did not
  cover it). Would give UDP path but cost is prohibitive for a home setup.
- WARP / Zero Trust private network: client-side WARP + cloudflared private routes carry arbitrary
  UDP/TCP over QUIC (MASQUE) to the cluster. Real UDP => WebRTC possible. Needs WARP client on every
  user device; adds ~edge hop RTT (your 52.8 ms hairpin) (C).
- Cloudflare Realtime TURN: UDP/TCP/TLS on 3478/80/443/5349, anycast-homed, per-allocation limits
  ~5-10 kpps and ~50-100 Mbps (enough for 30 Mbps ~ 3 kpps), $0.05/GB egress after free tier
  (conflicting docs: free with SFU / 1,000 GB free tier). A.
  https://developers.cloudflare.com/realtime/turn/ , .../turn/faq/ , .../realtime/sfu/pricing/
  Caveat: TURN relays UDP via CF POP -> your home needs outbound UDP to the relay; the relay hairpin
  is ~same 50 ms but UDP => no HoL, no retransmit stalls (C).

## Q3. Selkies 2.1 (source: github.com/selkies-project/selkies src/selkies/settings.py; protocol docs
https://docs.linuxserver.io/selkies/developer-guide/protocol/ ; deepwiki 2.2 page 429'd - not read)
- `mode`: websockets (default) | webrtc. `enable_dual_mode` true lets users switch in UI. A.
- backpressure_queue_size default 120 (1..100000): frames buffered per stream before drop.
  You tried 8; no effect => queue not the bottleneck, ack-based window is. A/C.
- Frame ack: server stamps uint16 frame id; client sends CLIENT_FRAME_ACK "a few times per
  second" (docs). Server computes desync = sent - acked minus smoothed RTT allowance; if beyond
  window it withholds frames; stalled client past a timeout is disconnected. Constants (window size,
  smoothing, timeout) NOT in docs; deepwiki (B, unread this run) mentions a 1000 ms latency
  forgiveness cap BACKPRESSURE_LATENCY_FORGIVENESS_MAX_MS. => read websockets_mode.py in repo for exact numbers.
  Low ack rate x jitter means coarse desync estimate => jerky withhold/resume. Check whether the
  web client's ack interval can be raised (per-frame or 60 Hz) - UNVERIFIED, needs code reading.
- `congestion_control` default true: on WS lowers CBR bitrate from frame round-trip queuing and
  jitter. With jitter it may oscillate. Try false (pinned bitrate). A (behavior), C (effect).
- `keyframe_interval` 0 = on demand only: after a withheld/dropped frame, recovery needs a keyframe
  = huge AV1/HEVC frame (at 30 Mbps/60fps ~ 62 KB avg; keyframe maybe 10x) -> multi-hundred-ms
  burst over TCP. Consider rate_control_mode cbr + `video_min_qp/max_qp` bounds, and intra-refresh
  if pixelflux supports it (UNVERIFIED).
- WebRTC mode: `webrtc_pacer` true; `webrtc_ice_lite`; `webrtc_public_ip` + `webrtc_udp_mux_port`
  (single UDP port, ideal for one port-forward); `webrtc_tcp_mux_port` (ICE-TCP fallback);
  `turn_*` incl. `turn_rest_uri` and `enable_cloudflare_turn` + cloudflare_turn_token_id /
  cloudflare_turn_api_token (built-in Cloudflare Realtime TURN support!). `rtc_config_json`
  overrides everything. A.
  Signaling still goes over the tunnel (cheap, low rate); media goes UDP. Caveat: is your
  AV1/NVENC encoder path available in webrtc mode? Encoder list in settings shows h264enc default
  and some encoders WS-only; verify AV1 in WebRTC (UNVERIFIED).
- High-latency recommendations: none documented. Closest: lower framerate/bitrate (you tried
  bitrate), keep keyframes on-demand, disable congestion_control.

## Q4. Alternatives ranked by expected gaming latency (C, no measurements)
1. Tailscale/WireGuard direct (NAT-punched UDP): ~LAN + WAN RTT(10-30 ms). Needs client install.
   Works with webrtc mode if ICE candidates are tailnet IPs (set webrtc_public_ip or use rtc.json).
   DERP relay fallback (~50+ ms) when punch fails. Good for the owner's own devices only.
2. Port-forward UDP (one port, webrtc_udp_mux_port) + `webrtc_public_ip` + signaling via CF
   tunnel: ~WAN RTT, no client install, works in any browser. Exposes one UDP port on router
   (WebRTC is DTLS-SRTP authenticated; signaling auth stays behind forwardAuth). Best browser-only option.
3. Cloudflare Realtime TURN with webrtc mode (built-in settings): UDP relay, adds ~CF hairpin
   (~50 ms) but no HoL blocking. No port-forward needed. Cost per GB: 30 Mbps ~ 13.5 GB/h
   (1,000 GB free tier may apply, B).
4. Port-forward 443 TLS directly to Traefik (DNS-only record, bypass CF): same WS/TCP design but
   removes edge legs; fewer HoL layers. Exposes origin IP; lose CF protection (WAF, hiding).
5. WARP -> cloudflared private route: UDP possible, requires WARP on clients; ~tunnel RTT.
6. Current: WS over CF Tunnel. Worst tail latency due to TCP HoL x 3 legs.

## Ranked changes (what / where / effect / effort / risk)
1. Switch to WebRTC + UDP mux port forward (#2 above).
   Where: Selkies env/settings `mode=webrtc`, `webrtc_udp_mux_port=<N>`, `webrtc_public_ip=<WAN IP>`,
   router/k8s UDP service (hostPort/LB) N; keep g. tunnel for signaling.
   Effect: expected to remove tail (p95 ~ LAN + RTT); strong theoretical, no measurement. Effort M, risk M (open UDP port).
2. Selkies WS tuning test: `congestion_control=false`, keep `backpressure_queue_size` default(120)
   or high, test with sim jitter. Where: Selkies settings (env SELKIES_*). Effort S, risk low. Effect unknown; diagnostic.
3. Cloudflare Realtime TURN via `enable_cloudflare_turn` (+ token id/api token) in webrtc mode.
   Effect: no HoL, ~ +50 ms median. Effort S-M, risk low. Cost small.
4. Tailscale for the owner's own devices (webrtc or WS direct). Effort S, risk low. Effect large for those users.
5. Gateway/Traefik TCP hygiene: ensure TCP_NODELAY on aiohttp proxy sockets (aiohttp sets by default), reduce
   proxy buffering (no buffering middleware on WS), set small SO_SNDBUF on the WS socket so the
   kernel queue does not hide delay (Selkies backpressure then reacts sooner). Effort M, effect
   uncertain (C). Check k8s: nodes' `net.ipv4.tcp_notsent_lowat` (e.g. 16384) on server side limits
   unsent queue; real, well-known for latency-sensitive streaming over TCP (C).
6. Update cloudflared to latest (quiche CC fix), edge-ip-version=auto test. Effort S, risk low, effect unknown.
7. Disable Rocket Loader/Polish/minify for g.; keep Argo off (incompatible with WS). S, none.
8. WARP/private route. M-L, risk low-med, requires client install.
9. Spectrum. Enterprise. Skip.

## Try first (3)
1. Re-run your jitter sim with `congestion_control=false` and tcp_notsent_lowat=16384 on the gateway/selkies
   node: tells whether Selkies backpressure / TCP queueing explains the tail, before touching Cloudflare.
2. Test webrtc mode over a single forwarded UDP port (`webrtc_udp_mux_port` + `webrtc_public_ip`),
   AV1 availability permitting; compare p95 on the real link.
3. If a port-forward is unacceptable, enable built-in Cloudflare Realtime TURN
   (`enable_cloudflare_turn`) in webrtc mode and measure.

## Sources
- https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/configure-tunnels/cloudflared-parameters/origin-parameters/
- https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/configure-tunnels/cloudflared-parameters/run-parameters/
- https://developers.cloudflare.com/network/websockets/
- https://developers.cloudflare.com/argo-smart-routing/
- https://developers.cloudflare.com/realtime/turn/ (+ /faq/), https://developers.cloudflare.com/realtime/sfu/pricing/
- https://developers.cloudflare.com/changelog/2025-07-15-udp-improvements/
- https://raw.githubusercontent.com/selkies-project/selkies/main/src/selkies/settings.py (first 100k chars)
- https://docs.linuxserver.io/selkies/developer-guide/protocol/
- https://deepwiki.com/selkies-project/selkies/2.2-websocket-streaming-service (search snippet only)
- https://blog.cloudflare.com/quic-death-spiral-fix/ (not read; via secondary summaries)

## Result 2026-11-01: congestion_control=false (results/20261101-0458-game01-tunnel-nocc)
Sim cf-tunnel, GAME-01 agent 0.9.27, AV1 NVENC 60 fps. Base p50 83–100 ms, p95 106–121, p99 ≤171.
congestion_control=false: same p50, worse tail (key p99 370, motion p99 1120). Keep default (true).
Base tail far better than 2026-10-31 run (p95 750–900) — that run predates agent 0.9.27 (#60 fps fix); likely cause. tcp_notsent_lowat untested (needs sudo).

## Result 2026-11-01: real cf-tunnel (results/20261101-*-game01-realtunnel)
Mini -> g.jmolabs.dev (CF) -> k3s -> GAME-01, agent 0.9.27, AV1 NVENC 60 fps, 100 samples/kind.
key p50/p95/p99 95/119/432; mouse 69/82/129; motion 64/72/106; 0 stalls. Beats the sim (sim jitter too pessimistic).
Key path consistently worst (tail 432) -> investigate key input path. WebRTC LAN for reference: 34/42/45, 35/45/50, 16/33/33.
