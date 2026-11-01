# Streaming pipeline

How pixels get from a seat to the browser, what we patch, and how we measure it.

The streaming engine is the [Selkies Project](../acknowledgements.md) (selkies, pixelflux and pcmflux); Styx wraps it with its own gateway.

## Pipeline

![Streaming pipeline from seat capture through pixelflux and selkies to the gateway, Traefik and the browser](../assets/diagrams/build-streaming-1-light.svg#only-light)
![Streaming pipeline from seat capture through pixelflux and selkies to the gateway, Traefik and the browser](../assets/diagrams/build-streaming-1-dark.svg#only-dark)

| Component | What it does |
|-----------|--------------|
| **pixelflux** | Rust capture and encode library: Wayland compositor mode, portal/PipeWire capture, VA-API (AMD/Intel) and NVENC encoders; software fallbacks (SVT-AV1, x264/x265) exist but Styx avoids advertising them |
| **pcmflux** | Audio capture/encode |
| **selkies 2.1** | Python server + web client: sessions, congestion control, input, clipboard, file transfer, the browser bundle |
| **Styx gateway** | Auth, idle, busy gate, size ownership, injected shims (see [Agent](agent.md)) |

Versions are pinned in `agent/enroll.sh` (selkies 2.1.0, pixelflux 2.2.1, pcmflux 2.2.0) and the wheelhouse built by
`scripts/build_agent_artifacts.sh`.

## Codec choice

`engine.build_selkies_cmd` passes an ordered encoder list; selkies picks the first
the browser can decode: **AV1, then HEVC, then H.264**. Hardware support is probed
once per render node ([Agent](agent.md#engine-enginepy)). Default bitrate is 30
Mbps CBR with a 1 Mbps floor; viewers may lower it, the admin value is the
ceiling. Paint-over re-sharpens text when the screen settles.

!!! note "AV1 on AMD VCN"
    radeonsi pads coded AV1 frames (width to x64) and Chromium ignores the render
    size, so text looked squeezed. Fixed by a pixelflux render-size patch plus a
    client-side crop that `bundle_patch.py` re-applies at every agent start. See
    [Upstream](upstream.md).

## Transports

| | WebSockets | WebRTC |
|---|---|---|
| selkies flag | `--mode=websockets` (default) | `--mode=webrtc` |
| Path | Everything over one HTTPS/WSS connection; works through the Cloudflare tunnel and any HTTP proxy | Signalling over WSS (`/api/webrtc/signaling/`), media over UDP/ICE, TURN when P2P is blocked |
| Congestion control | selkies' sender-side steering (below) | Browser WebRTC stack |
| Gateway features | Full: idle, busy gate, refit, shims | Signalling passthrough at the same path, idle and max-age cut via activity beacons, one viewer at a time (busy close code 4003), refit and fill |

!!! note "Choosing WebRTC"
    Set the default under **Admin → Settings → WebRTC / TURN** (*Default stream
    transport*: `websockets` or `webrtc`) or per workstation under **Stream
    settings → Transport**. TURN provider is `none`, `cloudflare` or `generic`.
    A TURN budget (default 900 GB) falls back to WebSockets when reached, and a
    WebRTC session ends after *WebRTC max session* hours (default 8). The idle
    cutoff is the workstation idle timeout. See [WebRTC and TURN](../operate/webrtc-turn.md).

## Congestion control and the shallow pipe

On the WebSocket transport selkies steers the bitrate to the link: it estimates
path capacity from acknowledgements and the standing queue above the round-trip
floor. Two Styx runtime patches (`agent/shallow_pipe.py`, `engine.cap_still_raise`)
address behaviour we measured on jittery links:

* **Owner lag gate** (`shallow_pipe.owner_gate`): upstream skips delta frames only for pages that do not own the display; the owner's frames can queue up to the 2 s relay budget, so a Wi-Fi hiccup becomes seconds of late video and the congestion controller overreacts. The patch gives the owner a 100 ms lag threshold (`OWNER_LAG_S`) and reuses the existing reference-invalidation recovery. It is **version-gated** to selkies 2.1.0 and logs a warning and turns itself off otherwise. Measured on hotel Wi-Fi: bitrate cuts over 30% per 5 min 6.45 -> 0, max extra queue 735 -> 42 ms. See [Upstream](upstream.md).
* **Still-screen raise cap** (`cap_still_raise`): selkies raised the CBR target 15% per second on every clean tick, including a still screen's trickle, so after a backoff it climbed to the ceiling without testing the path and the next burst built a queue (the "poor connection" sawtooth). The patch remembers the last measured capacity and only lets motion raise past it. Tracked upstream as selkies#489.
* **Tracing**: `STYX-CC` lines in `selkies.log` (queue, RTT floor, delivered rate, target rate) feed `docs/spikes/2026-10-30-shallow-pipe/cc_report.py`.

![Congestion control loop: encoder, network, browser acknowledgements and selkies adjusting the target bitrate](../assets/diagrams/build-streaming-2-light.svg#only-light)
![Congestion control loop: encoder, network, browser acknowledgements and selkies adjusting the target bitrate](../assets/diagrams/build-streaming-2-dark.svg#only-dark)

Both are marked `ponytail:` in code as temporary: drop them when upstream fixes land.

## Latency and A/B harness (`e2e/stream-ab/`)

An unattended harness that drives a real seat with a headless Chromium through a
**userspace network emulator**, so codec and bitrate changes are judged on numbers.

!!! warning "Run it only on a lab seat"
    It restarts selkies on the host it runs on, and needs the seat idle (the
    gateway's busy gate refuses a second controller). Do not run it on a
    workstation someone is using.

| File | Role |
|------|------|
| `ab.py` | Orchestrator: for each variant writes `stream-override.json`, restarts only selkies, opens the workload page, runs each network profile, summarises `selkies.log` |
| `netem.py` | TCP proxy shaping the server-to-client direction (rate, one-way delay + jitter, periodic collapses, loss, outages) |
| `run.mjs`, `latency.mjs`, `workload.html` | Playwright drivers and the page that scrolls, types and plays motion |
| `probes.py` | Samples CPU, GPU (VCN busy, VRAM/GTT) and RSS during a run |
| `soak.py` | Long run to catch memory growth, selkies crashes and watchdog restarts |
| `suite.sh` | Full unattended A/B + outage + soak (~90 min) |
| `suite_latency.py`, `latstats.py` | Gaming latency suite and its pure statistics |
| `test_*.py` | Unit tests for the pure parts |

Credentials are read from the agent's own config and passed by env, never argv.

```bash
cd e2e/stream-ab
python3 ab.py --variants h264-16,av1-30 --profiles hotel,office --repeats 2   # A/B
python3 ab.py --variants av1-30 --profiles drop3,drop10,drop30                # outage recovery
python3 soak.py --variant av1-30 --minutes 60                                 # soak
python3 ab.py --suite latency --dry-run                                       # plan + time estimate
python3 ab.py --suite latency --quick                                         # av1-60 / h264-120 on lan, cf-tunnel
sh suite.sh                                                                   # everything, ~90 min
```

Results land in `results/<stamp>.json` and `.md`.

**Variants** (`ab.py VARIANTS`): `h264-16`, `h264-30`, `av1-16`, `av1-30`, and the
latency set `av1-60`, `av1-120`, `h264-60`, `h264-120` (all 30 Mbps CBR; frame
rate as `initial,min-max`).

**Network profiles** (`netem.py PROFILES`): `lan`, `office` (100 Mbps, 5 ms +
0-2 ms), `hotel` (45 Mbps, 20 ms + 0-70 ms, 3 s collapse to 1 Mbps each minute),
`hotspot`, `cf-tunnel` (Cloudflare hairpin, ~52 ms median RTT), `wifi-loss`
(0.5% loss plus jitter bursts), and `drop3/10/30` (link vanishes once).

### What the metrics mean

| Metric | Meaning |
|--------|---------|
| `latP50` / `latP95` | Key press to first decoded frame showing the change |
| `sharpStill`, `sharpAfterScroll`, `sharpEnd` | Laplacian variance of a text screenshot; higher is crisper |
| `cuts_gt30_per5m` | Congestion bitrate cuts over 30% per 5 minutes |
| `lost` | Frames reported lost |
| `maxGapMs` | Longest gap between presented frames |
| `vcn_mean`, `cpu_mean`, `rss_mb_growth` | Encoder busy %, CPU, memory growth |
| `valid` | False if a foreign client connected, the watchdog restarted selkies, or the motion check failed (codec fell back, etc.) |
| Latency suite: `p50/p95/p99`, `std`, `>100ms`, `miss%`, `stalls`, `pacing sd` | Input-to-photon per input kind (key, mouse, motion), jitter, slow-sample count, missed samples, frame stalls above 50 ms |

### Findings (2026-10-30, Radeon 780M, GNOME seat 2560x1440 @2x)

Source: `e2e/stream-ab/RESULTS-2026-10-30.md`.

| | settled text sharpness | latency p50/p95 office | latency p50 hotel | encoder busy |
|---|---|---|---|---|
| H.264 16 Mbps (old default) | 3627-3875 | 53-54 / 74-78 ms | 117-121 ms | ~26% |
| AV1 30 Mbps (default since agent 0.9.19) | **5034-5039 (+35%)** | 50-51 / 78-96 ms | 140 ms (1 run) | ~25% |

* Earlier rounds agree: settled text 15-39% crisper at the same cut and drop counts. A browser refusing AV1 streams H.264.
* **Outage recovery** (office link vanishes once): 3 s, 10 s and 30 s outages produced gaps equal to the outage (3.02 / 10.005 / 30.02 s), with the picture back within ~20 ms of the link returning and no reconnect or watchdog.
* **Soak** (AV1 30 Mbps, 60 min, 34 cycles): 0 crashes, 0 watchdog restarts, p50 latency steady at 51 ms, selkies RSS 180 -> 184 MB, VRAM flat after start-up.
* Harness lessons: the first session after a selkies restart can go frameless for 15 s (so `ab.py` discards a warm-up run); selkies re-writes its last frame about every 1.2 s when idle (frames are counted by timestamp); first-run browser dialogs can eat input.

## Known limits

* **Second screen** is disabled (`--second-screen=false`); an upstream limit.
* **Mirror mode** is X11 only; Wayland hosts use a seat.
* **One controller** per seat. Others see "in use elsewhere" (close code 4003) or can join read-only with `role=viewer`.
* **Printing, microphone, webcam, gamepad, 10-bit** are disabled and locked in the engine command until their phases ship.
* **4:4:4 chroma** is opt-in: no AMD/Intel VA-API driver encodes H.264 4:4:4, so selkies would fall back to CPU x264.
* **Software AV1/HEVC are never offered**; a host without a hardware encoder streams H.264 only.
* Browser decode support varies: HEVC availability depends on the browser and OS; AV1 is not available everywhere.
* AV1 on pre-VCN-5 AMD needs the crop patch; Intel, NVIDIA and other AMD generations are untested for padding.
* Selkies 2.1 reserves close codes: `4001` (final, no reconnect) is used for idle timeout and a close reason containing "superseded" disables auto-reconnect.
