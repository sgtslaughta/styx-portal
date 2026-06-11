# Workstation Streaming v2 — Native pixelflux Engine

**Date:** 2026-06-11
**Status:** Approved (design); Phase 0 spikes pending
**Supersedes:** the selkies-gstreamer 1.6.2 tarball engine in `agent/styx_agent.py`
(enrollment chain, routing, and backend are retained).

## Problem

The shipped workstation agent uses the selkies-gstreamer 1.6.2 portable tarball.
Live debugging on real hardware proved it unfit:

- WebRTC transport: proxy-hostile, requires STUN/TURN; Cloudflare tunnel is
  TCP/WebSocket-only.
- Portable tarball bundles a CPU-only GStreamer (x264enc/vp8enc); no NVENC or
  VA-API. No gaming-grade performance.
- Bundled python interpreter conflicts with user site-packages (ABI crashes).
- X11-only; no Wayland story.
- A stock `ghcr.io/linuxserver/baseimage-selkies` container cannot mirror the
  host display: it unconditionally boots its own internal display (verified
  empirically — captured its own 1024x768 Xvfb, not the host 2056x1176 session).

## Goal

Native-desktop experience on physical Linux workstations: the user's own files,
apps, and (where possible) live screen — streamed to a browser with audio,
GPU-encoded, gaming-capable, through the existing Traefik + Cloudflare-tunnel
WebSocket path. Easy install, easy removal, robust across mainstream distros.
The user's physical session is duplicated/mirrored, never stolen.

## Decision

Replace the streaming engine with the **selkies 2.x stack installed natively
into a venv** from prebuilt wheels — no container on the workstation, no
bundled interpreter, no GStreamer.

Components (all from the linuxserver/selkies 2.x ecosystem):

| Component | Source | Role |
|---|---|---|
| `pixelflux` (>=1.6.4) | PyPI, manylinux_2_34/musllinux wheels, cp38–cp314, x86_64+aarch64 | Screen capture + encode: XShm capture of an existing X11 display, or own headless Smithay Wayland compositor (`PIXELFLUX_WAYLAND`). Encoders: x264, JPEG, NVENC, VA-API. Striped change-detection encoding. |
| `pcmflux` (>=1.0.8) | PyPI, manylinux_2_28 wheels | Audio capture/encode (PulseAudio/PipeWire source → Opus). |
| `selkies` 2.x app | Pinned git tarball from `selkies-project/selkies` (commit pinned in agent config; not yet on PyPI — PyPI `selkies` 1.6.1 is the legacy GStreamer app) | WebSocket streaming server (`SelkiesStreamingApp`): drives pixelflux/pcmflux, handles input, serves data websocket. |
| Web dashboard | Prebuilt dist (selkies-web-core); vendored as portal artifact | Browser client UI. |

### Why this beats the alternatives evaluated

Six options were scored (matrix in brainstorm, 2026-06-11): thin mirror
container, native second-seat, dual-backend portal mirror, Sunshine +
moonlight-web, KasmVNC + Kclient, xpra shadow. Native pixelflux won on:
selkies-stack alignment, pure-WebSocket transport (tunnel-clean), GPU encode,
single code path for X11 *and* Wayland hosts, no Docker requirement on
workstations, trivial removal. Decisions made:

- **Wayland true pixel-mirror is out of scope.** Wayland hosts get a
  full-quality *second-seat* virtual session (same user, same files, host
  apps) instead. Portal/PipeWire mirror can be grafted on later as its own
  project (upstream tracking: selkies-project/selkies#46, open since 2022).
- **Native everywhere** (not hybrid container+native): prebuilt wheels remove
  the compile/ABI risk that motivated containers; one install path.

## Architecture

### What is retained unchanged

- Enrollment: token mint UI → `enroll.sh` (E-code preflight) → `/api/enroll`
  register → config.json (0600) → systemd user unit.
- Agent lifecycle: heartbeat, doctor, uninstall, deregister.
- Routing: Traefik `/w/{sub}` routers + ws forward-auth + credential
  injection; host-agnostic LAN routers; LAN TLS + pinned bootstrap.
- Backend: models, routers, schemas (minor additions only, e.g. new
  `display_server` value semantics and doctor/health fields).

### Engine modes

Mode auto-detected at agent start; `--display-mode mirror|seat` override kept.

**Mirror mode** — host session is X11 (`XDG_SESSION_TYPE=x11` or a live X
socket + resolvable XAUTHORITY):
- pixelflux XShm capture of the live display (`:0`, `:1`, …) using the
  existing `_find_xauthority()` resolver.
- Input: shared control of the real session (standard VNC semantics; the
  physical cursor moves). This is duplication, not session theft — the local
  user keeps full control.
- Audio: pcmflux capturing the host PulseAudio/PipeWire **monitor source** of
  the default sink.

**Second-seat mode** — host session is Wayland, or no graphical session:
- pixelflux headless Smithay compositor (GPU framebuffer via /dev/dri DMABUF,
  Pixman/LLVMpipe fallback).
- Lightweight shell: `labwc` (installed from distro repos by preflight) +
  host applications launched inside the seat. Xwayland availability for
  X11-only host apps: validated by Spike 2.
- Audio: own virtual sink via pcmflux.
- Isolated input; physical session untouched.

**Encoders** (both modes): probe order NVENC → VA-API → x264. pixelflux owns
the probing/fallback; agent records the chosen encoder for doctor/heartbeat.

### Transport

selkies 2.x WebSocket protocol end to end: agent binds `0.0.0.0:<port>`
(default 8443) → Traefik `/w/{sub}` route (LAN + tunnel) → browser dashboard.
No WebRTC, no STUN/TURN, no UDP. Credentials stay in env
(`SELKIES_BASIC_AUTH_*`), never argv.

### Install layout & removal

```
/opt/styx-agent/
  venv/            system python3 venv (pixelflux, pcmflux, selkies, deps)
  web/             dashboard dist
  config.json      0600
```
systemd user unit `styx-agent.service` (existing pattern). Removal =
stop+disable unit, `rm -rf /opt/styx-agent`, deregister. Nothing else touched.
`/opt` is created with sudo during enrollment (enroll.sh already escalates for
distro package installs) and chowned to the enrolling user.

### Distribution

- **Prod:** wheels from PyPI; selkies app tarball + web dist served by the
  portal artifact cache (same mechanism as today's tarball cache) so
  enrollment works without workstation-side GitHub access and versions are
  pinned by the portal.
- **Dev:** pip install from local repo checkout / portal-served bundle.

### Preflight additions (enroll.sh)

| Check | Action |
|---|---|
| glibc ≥ 2.34 (wheel floor) | hard fail, E-code: "distro too old (need Ubuntu 22.04+/Debian 12+/RHEL 9+)" |
| python3 ≥ 3.10 + venv module | hard fail or auto-install via distro pkg mgr |
| Session type detect (loginctl/XDG_SESSION_TYPE) | selects default mode |
| Audio server (pipewire/pulseaudio socket) | warn → audio disabled |
| /dev/dri render node | warn → CPU encode |
| labwc (second-seat only) | auto-install via apt/dnf/pacman/zypper |

## Phase 0 spikes (gate before full implementation)

Run on this machine (live X display, AMD iGPU, PipeWire):

1. **Mirror spike:** venv + wheels + pinned selkies app; capture the live X
   display; verify browser stream (resolution matches physical session) and
   VA-API encode engages. Highest-risk item — kills the project if it fails.
2. **Second-seat spike:** `PIXELFLUX_WAYLAND` compositor + labwc + one host
   GUI app; record Xwayland status.
3. **Audio spike:** pcmflux capture of the default-sink monitor source.

Each spike result is recorded in this spec's companion notes before the
implementation plan is written.

### Spike results (2026-06-11, Ubuntu 24.04 / AMD iGPU / PipeWire — ALL PASS)

1. **Mirror: PASS.** selkies 2.x (pinned commit 0d134b6) + pixelflux attached
   to a pre-existing external X display, streamed 60 H.264 stripe frames at
   the display's true resolution over the data websocket, and
   **"VAAPI Encoder Initialized successfully"** with `--dri-node`
   (`DRI_NODE` env). The `display=1024x768` init log line is a constructor
   placeholder, not the capture size — the earlier container POC conclusion
   was a misread; capture sizing is correct.
2. **Second-seat: PASS (with shim).** `PIXELFLUX_WAYLAND=true` brought up the
   Rust compositor (GL renderer on `/dev/dri/renderD128`), created a
   `wayland-N` socket, a host GTK app (gnome-calculator) ran as its client,
   and frames flowed. Remaining sub-validation: nested `labwc` as WM +
   Xwayland for X11-only host apps (labwc not installed on the test box).
3. **Audio: PASS.** pcmflux connected to the default-sink monitor source via
   PipeWire's pulse shim and streamed Opus chunks over the same websocket
   after `START_AUDIO`. The agent must resolve `<default-sink>.monitor`
   dynamically (selkies' default `output.monitor` only matches by luck here).

**Critical compat finding — the libva/libwayland floor.** pixelflux wheels
≥1.5.x bundle an ffmpeg that requires system `libva ≥ 2.21`
(`vaMapBuffer2`), and the Wayland backend requires `libwayland-server ≥ 1.23`
(`wl_client_set_max_buffer_size`). Ubuntu 24.04 LTS ships libva 2.20 /
libwayland 1.22 — pixelflux 1.6.4 fails to load both backends there.
Validated fix: a **private lib shim** — ship `libva.so.2` (2.22),
`libva-drm.so.2`, and `libwayland-server.so.0` (1.23) in the agent's lib dir
and set `LD_LIBRARY_PATH` for the selkies process only (~1 MB total; both
backends then load and stream). Alternative validated fallback: pixelflux
1.4.7 works on stock libva 2.20 but has no Wayland backend (mirror-only).
Decision: ship the shim, pin pixelflux 1.6.4 everywhere — uniform engine,
no per-distro version forks. Portal serves shim libs as artifacts.

**Other implementation facts learned:**
- `setuptools` must be installed alongside selkies (GPUtil imports
  `distutils`, removed in py3.12).
- pip dep `xkbcommon` is source-only — needs `libxkbcommon-dev` + gcc at
  install (preflight), or we serve a prebuilt wheel from the portal (the
  portal-wheel route is preferred; zero compiler requirement on hosts).
- Client protocol (for dashboard/web vendoring + tests): ws path
  `/websocket`, client sends `SETTINGS,{json with displayId:"primary",
  initialClientWidth/Height}`, then `START_VIDEO` / `START_AUDIO`; binary
  stripe frames downstream; full config via `SELKIES_*` env vars.
- Web dist lives at `/usr/share/selkies/web` in linuxserver images; nginx
  proxies `/websocket` → `127.0.0.1:8082` (we mirror this in agent + Traefik).
- Seat mode wants `wl-clipboard` (clipboard) — preflight auto-install.
- Resolution management: selkies resizes the display to the client viewport
  by default (`is_manual_resolution_mode=False`). Fine for second-seat;
  mirror mode must lock to the physical display's current resolution.

## Known risks

| Risk | Mitigation |
|---|---|
| selkies 2.x has no PyPI release; API may shift | pin exact commit; portal-cached tarball; spike validates |
| Web dashboard built separately upstream (selkies-web-core) | vendor prebuilt dist as portal artifact |
| Smithay Xwayland support uncertain | Spike 2; if absent, second-seat is Wayland-native apps only at launch |
| glibc < 2.34 distros unsupported | explicit preflight E-code |
| Mirror mode needs resolvable XAUTHORITY | resolver already shipped + doctor surfaces failure clearly |
| pixelflux/selkies upstream churn (linuxserver-driven) | portal pins all artifact versions; agent reports versions in heartbeat |

## Testing

- Agent unit tests: mode detection, command/env construction, encoder
  recording, preflight parsing (existing suite extended).
- Backend: existing 293+ tests unchanged; additions for new health fields.
- Live validation: spikes now, then real-machine smoke test per mode.

## Out of scope

- Wayland true pixel-mirror (future: portal/PipeWire capture feeding the same
  WebSocket protocol).
- Multi-monitor selection UI, collaborative multi-user input arbitration.
- Non-Linux workstations.
