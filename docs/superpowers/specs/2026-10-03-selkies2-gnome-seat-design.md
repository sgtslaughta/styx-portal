# Selkies 2.0 + Headless GNOME Seat — Design

- **Date:** 2026-10-03
- **Status:** Approved in brainstorming (sections 1–5); pending written-spec review
- **Agent target:** 0.5.0 (Phase 0), minor bump per later phase
- **Evidence:** spike on EliteMini 2026-10-03 (see "Spike findings")

## 1. Goal

Replace the streaming stack on enrolled workstations with upstream Selkies 2.0
(pixelflux 2.1 / pcmflux 2.1) and replace the labwc/waybar/nwg "GNOME-like" seat
with a **real headless GNOME session**, then expose the new Selkies features
(codecs, native clipboard/files, audit, devices, sharing, WebRTC) through the
portal's existing settings model.

### Why

- Today's engine (selkies `0d134b6`, pixelflux 1.6.4) freezes video after long
  uptime ("Waiting for stream" with audio alive). pixelflux 2.0 fixes a blocking
  encode channel that stalls the compositor loop and a stop/start deadlock.
- 2.x brings VA-API/NVENC rewrites, zero-copy capture, H.265/AV1, ~30% lower
  latency on x264 striping, silence-gated audio, loopback-by-default binding.
- Users want a true Ubuntu desktop; the spike proved headless GNOME 46 streams
  through Selkies 2.0 with native look, good audio, responsive input.

### Success criteria

- Both boxes stream the GNOME seat through Cloudflare with all Phase 0 live
  checks (§7.3) passing and no backend/agent test regressions.
- No "Waiting for stream" lock-ups in a 24 h soak; memory flat.
- Every later phase ships behind system-default + per-workstation toggles.

### Out of scope

Recording, Computer Use API, WebRTC without TURN, KDE seat, frontend toolchain
major upgrades, splitting `backend/app/routers/instances.py`.

## 2. Spike findings (constraints this design obeys)

1. `gnome-shell --headless --wayland --no-x11 --virtual-monitor WxH
   --wayland-display=<sock>` under its own `dbus-run-session` runs beside the
   physical session and the old seat. Load ≈ 5% selkies + 4% gnome-shell.
2. GNOME offers no screencopy, so pixelflux captures via **xdg-desktop-portal**
   ScreenCast + RemoteDesktop (input via libei). First use needs **one consent
   click**; pixelflux then stores a restore token at
   `~/.local/state/pixelflux/portal-restore-token` and later sessions start
   without a prompt (verified).
3. The consent dialog renders on whatever display the session bus's
   **activation environment** names. Inheriting `DISPLAY=:1` put it on the
   physical desktop. The activation env must be set before any portal starts.
4. **Cursor:** the portal path forwards no cursor metadata to the client; the
   cursor is baked into video → double cursor, flicker on move, stale cursor on
   leave. `--use-browser-cursors` does not help. Upstream gap.
5. **Resolution:** the virtual monitor does not follow the browser size.
6. Headless-session apps play to the default sink unless `PULSE_SINK` is set.
7. 2.0 protocol: WS path `/api/websockets`; client must send codec caps before
   video flows; no audio packets during silence; audio frames start `0x01`,
   video frames start `0x04` (codec in high nibble, kind in low nibble).
8. Cloudflare Tunnel cannot carry WebRTC media (UDP) → TURN required remotely.

## 3. Architecture

```
Browser ──Cloudflare/Traefik──▶ gateway.py  (auth, visibility shim, idle closer,
                                  stall watchdog, cursor workaround inject)
                                     │ single upstream: http + ws → 127.0.0.1:<port>
                                     ▼
                           selkies 2.0  (pip wheel; serves client + /api/*)
                                     │ --wayland-host-display=styx-seat-0
                                     ▼ portal ScreenCast / RemoteDesktop (libei)
           seat session: dbus-run-session → gnome-shell --headless
                         --virtual-monitor WxH, PULSE_SINK=styx-seat,
                         activation env scrubbed (no DISPLAY leak)
```

### 3.1 Agent components

| Unit | Responsibility | Depends on |
|---|---|---|
| `agent/seat_gnome.py` (new) | Start/supervise headless GNOME: private bus, scrubbed env, activation env, sink, virtual monitor, readiness, restart/backoff | gnome-shell ≥ 46, dbus-run-session |
| `agent/engine.py` (slimmed) | Pure functions: build selkies 2.0 argv/env from effective settings; seat-shell selection | settings dict |
| `agent/gateway.py` | Auth, single-upstream proxy (`/`, `/api/websockets`, `/api/*`), idle closer, stall watchdog (`0x04` video / `0x01` audio), visibility shim, cursor workaround inject | aiohttp |
| `agent/styx_agent.py` | Supervisor, heartbeat, doctor (incl. `--grant`), rollback | above |
| Deleted (Phase 0) | `selkies_launcher.py` (2.0 binds loopback natively) | — |
| Deleted (Phase 2) | `clipboard_bridge.py`, gateway file handling | — |

`engine.py` and `styx_agent.py` must end Phase 0 under 500 lines each.

### 3.2 Seat lifecycle

- The GNOME session lives as long as the agent; apps survive viewer reconnects.
- Engine (selkies) restarts never restart the session. Only a gnome-shell exit
  or the escalation rule in §5 restarts it.
- `seat_shell` setting: `gnome` (default) | `labwc` (existing seat kept as
  fallback; selected per workstation or auto-chosen when GNOME preflight fails).

### 3.3 Selkies 2.0 invocation (Phase 0 baseline)

| Concern | 2.0 flag / env |
|---|---|
| Port / bind | `--port=<internal>`; default loopback bind (no `--public`) |
| Auth | `--enable-basic-auth=false` (gateway owns auth) |
| Transport | `--mode=websockets` |
| Capture | `--wayland=true --wayland-host-display=styx-seat-0` |
| GPU | `--encode-dri=<node> --render-dri=<node>` |
| Encoder | `--encoder=h264enc` (Phase 1 opens the list) |
| Frame rate | `--framerate=<fps>` |
| Second screen | `--second-screen=false` |
| Audio | `--audio-device-name=styx-seat.monitor` |
| Quality | `SELKIES_VIDEO_CRF`, `SELKIES_VIDEO_STREAMING_MODE`, `SELKIES_VIDEO_PAINTOVER_CRF` |
| Fixed-res fallback | `--manual-width/--manual-height` |
| Feature defaults | printing/mic/webcam/gamepad off until their phase enables them |

Removed flags: `--control-port`, `--dri-node`, `--is-manual-resolution-mode`,
`--wayland-socket-index`. Because 2.0 only *warns* on unknown flags, a test
validates every emitted flag against the installed wheel's
`selkies/settings.py` definitions.

### 3.4 Artifacts

Pinned wheelhouse built on the server: `selkies==2.0.0`, `pixelflux==2.1.0`,
`pcmflux==2.1.0` + deps. The selkies web client ships inside the wheel; the
linuxserver base-image extraction step is removed. No toolchains or PPAs on
enrolled boxes.

## 4. Settings model

- **System defaults:** new "Workstation features" category in
  `backend/app/services/settings_store.py` (same mechanism as idle timeout).
- **Per-workstation overrides:** keys in existing `stream_settings` JSON;
  absent key = inherit default.
- **Single resolver** in the heartbeat path (`backend/app/routers/agent.py`)
  merges override over default and returns effective values; the existing
  idle-timeout folding moves into it.
- **Rename:** `h264_crf`, `h264_streaming_mode`, `h264_paintover_crf` →
  `video_*`. Additive DB migration writes `video_*` beside old keys; old keys
  removed one release later. Agent 0.5.x accepts both names.
- **Version gating:** backend sends 2.0-only keys only to `agent_version ≥
  0.5.0`; 0.4.x agents receive today's shape.
- **Permissions:** device (mic/webcam) and sharing toggles are admin-only.

New keys (default in brackets), introduced by phase:

| Phase | Keys |
|---|---|
| 0 | `seat_shell` [gnome], `seat_width`/`seat_height` [2560/1440], `cursor_workaround` [true] |
| 1 | `video_codec` [h264], `video_codecs_allowed` [h264,h265,av1], `video_crf`, `video_fullcolor` [false], `rate_control` [crf], `video_bitrate_kbps` |
| 2 | `clipboard` [true: both ways], `clipboard_binary` [true], `file_transfers` [upload,download], `file_transfer_limit_mbps` [0 = adaptive] |
| 3 | `audit_enabled` [true] (webhook URL/token generated by backend) |
| 4 | `microphone` [demand], `webcam` [demand], `gamepads` [false], `printing` [false] |
| 5 | `sharing` [false], `share_modes` [viewonly] |
| 6 | `transport` [websockets] (`websockets` / `dual`), TURN creds via system settings |

## 5. Data flow and error handling

### 5.1 Startup

1. Resolve effective settings (heartbeat; cached copy when offline).
2. `seat_gnome` runs `dbus-run-session -- <launch script>`. The launch script:
   unsets `DISPLAY`, `WAYLAND_DISPLAY` and physical-session vars; exports
   `PULSE_SINK=styx-seat`; runs `dbus-update-activation-environment
   DISPLAY= WAYLAND_DISPLAY=styx-seat-0 XDG_SESSION_TYPE=wayland
   XDG_CURRENT_DESKTOP=ubuntu:GNOME PULSE_SINK=styx-seat` **before** exec;
   execs `gnome-shell --headless --wayland --no-x11 --virtual-monitor WxH
   --wayland-display=styx-seat-0`.
3. Readiness: socket exists and `org.gnome.Shell` answers on the private bus.
4. Engine starts selkies on that bus (§3.3).
5. Gateway starts with one upstream.
6. Each step's state is written to `state.json`; heartbeat + `doctor` report
   the failing step.

### 5.2 Viewer connect

Browser → gateway (auth; inject visibility shim, idle UX, cursor workaround) →
selkies `/api/websockets` → portal session (restore token) → frames.

**Cursor workaround:** injected CSS hides the browser cursor over the video
element; the in-video cursor is the only cursor (removes flicker and stale
cursor; adds one encode RTT of cursor lag). Controlled by `cursor_workaround`;
removed once upstream forwards cursor metadata.

### 5.3 Resize

Viewer size reaches selkies; the agent applies a new mode to the virtual monitor
via `org.gnome.Mutter.DisplayConfig`. **Phase 0 task 1 is proving this works on
a `--virtual-monitor`.** If not, the seat runs at fixed `seat_width×seat_height`
and the client scales (spike behavior).

### 5.4 Failure handling

| Failure | Detection | Response |
|---|---|---|
| No video at start / mid-session stall | gateway: no `0x04` frame 15 s while connected (stall: input arriving, frames stopped); selkies "delivered no frame" log | Restart **selkies only**. 3 restarts in 10 min → restart GNOME session, heartbeat `degraded` |
| selkies exits | supervisor | Restart with backoff (supervised forever) |
| gnome-shell exits | supervisor (pid + socket) | Restart session then selkies; heartbeat `seat_restarts` counter |
| Consent missing/revoked | portal `Start` pending > 20 s | Heartbeat `needs_consent`; portal UI shows "run `styx-agent doctor --grant` on the box" instead of black screen |
| Consent dialog on physical display | Prevented by §5.1 env scrub; unit test asserts it | — |
| Seat sink missing | engine preflight | Recreate `styx-seat` |
| gnome-shell missing / < 46 | doctor + engine preflight | Fall back to `labwc` seat; doctor advisory |

### 5.5 Consent grant (`styx-agent doctor --grant`)

No portal stream exists before consent, so the grant uses Mutter's
consent-free D-Bus APIs on the seat's private bus (proven in the spike for
capture):

1. Start the seat if needed; start selkies so it opens the portal request (the
   dialog renders on the seat display, per §5.1).
2. Capture a PNG of the seat via `org.gnome.Mutter.ScreenCast` and locate the
   dialog; accept it with `org.gnome.Mutter.RemoteDesktop` input (keyboard
   focus + Enter, or a pointer click on the "Share" button).
3. Success = restore token file appears and the first portal frame is logged;
   print the PNG path for the admin to inspect on failure.
4. **Fallback mode** `--grant --local`: set the activation env `DISPLAY` to the
   box's physical display for one request so a person at the box clicks Allow
   (the spike's accidental path), then restore the scrubbed env.

Phase 0 ships whichever of steps 2/4 is proven; step 2 is preferred.

### 5.6 Shared-profile caveat (documented, accepted)

The seat runs as the same Linux user as the physical login: dconf, extensions,
wallpaper, keyring are shared. Single-instance apps (browsers) get a
seat-specific profile directory, as today.

### 5.7 Security

- selkies binds loopback only; auth disabled behind the gateway; no new ports.
- Restore token is user-owned, mode 600.
- Never `--unsafe-mode`.
- Audit webhook token is generated per workstation by the backend.
- Share links are portal-minted and revocable; no selkies master token leaves
  the box.

## 6. Phases

Each phase is its own branch, merged to `main` when its acceptance passes.

| # | Branch | Ships | Acceptance |
|---|---|---|---|
| 0 | `feat/selkies2-phase0-engine` | §3–§5: 2.0 engine, GNOME seat (+labwc fallback), single-upstream gateway, cursor workaround, `doctor --grant`, wheelhouse, rename, agent 0.5.0 | §7.3 checklist on both boxes; 24 h soak; no test regressions |
| 1 | `feat/selkies2-phase1-codecs` | Codec choice + allowed list, quality knobs UI, resolution mode | Live codec switch on VA-API + NVENC; browser fallback when undecodable |
| 2 | `feat/selkies2-phase2-clipboard-files` | Native rich clipboard + file transfer; delete bridge + gateway file handling | Text+image clipboard both ways; upload/download within limits |
| 3 | `feat/selkies2-phase3-audit` | Webhook → `POST /api/audit` → audit log page | Clipboard/file/print/connect events per user+workstation |
| 4 | `feat/selkies2-phase4-devices` | Mic + webcam (on demand), gamepads (uinput when present), printing | Each verified in a real app |
| 5 | `feat/selkies2-phase5-sharing` | Portal-minted view-only/collab links via selkies tokens/roles | Link works through gateway; revocation is immediate |
| 6 | `feat/selkies2-phase6-webrtc` | Opt-in dual mode via Cloudflare TURN | GAME-01 latency/loss comparison vs WS; WS fallback works |

## 7. Testing

### 7.1 Unit (TDD, pytest, no GPU)

- `engine.py` argv/env builder: exact command per setting; every emitted flag
  exists in the installed wheel's `settings.py`.
- `seat_gnome.py`: launch-script env (no `DISPLAY`, `PULSE_SINK` set,
  activation env before exec), readiness, restart/backoff with fake processes.
- `gateway.py`: `0x04`/`0x01` classification, stall re-arm, single-upstream
  routing, injected cursor CSS + visibility shim; existing idle tests pass.
- Backend: resolver (default/override/effective), rename migration, version
  gating, heartbeat states (`needs_consent`, `degraded`), per-phase endpoints.
- Frontend: component tests for new toggles; gate on `npm run build`.

### 7.2 Integration

In-memory DB + fake agent heartbeat: effective settings for 0.4.x vs 0.5.0.

### 7.3 Live acceptance (Phase 0, both boxes, via Cloudflare)

1. First frame < 3 s.
2. Reload and load-while-tab-hidden both stream.
3. Idle timeout closes; Reconnect works.
4. Kill selkies mid-session → recovers, open apps survive.
5. Kill gnome-shell → session restored.
6. Delete restore token → portal shows `needs_consent`; `doctor --grant` fixes.
7. Browser resize → monitor follows (or scales on fallback).
8. Audio, text clipboard, keyboard layout, CapsLock.
9. Firefox in seat while the physical session also runs Firefox.
10. GAME-01 NVENC: load/latency vs 0.4.11.
11. 24 h soak on EliteMini: memory flat, no lock-ups.

### 7.4 CI

Existing pipelines + the wheel-flag validation test.

## 8. Rollout

### 8.1 Before Phase 0

1. Merge `fix/watchdog-ignore-audio` (agent 0.4.11) to `main`; roll to GAME-01.
2. Audit quick fixes as separate small branches: stale-seat clear in
   `mark_stale_offline`, frontend healthcheck `127.0.0.1`, backend security
   bumps (cryptography 50, PyJWT 2.15, Authlib 1.8, fastapi), CI (GitLab
   node:20, older GH actions), pin traefik/cloudflared/socket-proxy images.
3. File upstream issues: portal cursor metadata (GNOME), Mutter-direct capture
   (removes consent), headless virtual-monitor resize.

### 8.2 Per box

1. Build artifacts on the server.
2. EliteMini: update to 0.5.0, run `doctor --grant` once, run §7.3 + soak.
3. GAME-01: same + NVENC checks.
4. Rollback: 0.4.11 install kept side by side; `styx-agent rollback` restores
   code + wheelhouse. Old `h264_*` keys still honored.

### 8.3 Versions

Agent semver: 0.5.0 (Phase 0, breaking engine), minor bump per later phase.
Backend via semantic-release from conventional commits.

### 8.4 Docs

Zensical pages: GNOME seat requirements (GNOME ≥ 46, one-time consent),
shared-profile caveat, feature toggles, WebRTC/TURN setup. Fix stale comment
`backend/app/config.py:58` and `backend/app/services/artifacts.py:7`.

### 8.5 Removed at end of Phase 0

`agent/selkies_launcher.py`, labwc config not needed by the fallback, the
linuxserver base-image step in `scripts/build_agent_artifacts.sh`, the
`pixelflux==1.6.4` pin in `agent/enroll.sh`, legacy `/websocket(s)` routes.

## 9. Open risks

| Risk | Mitigation |
|---|---|
| Virtual monitor cannot resize | Fixed-resolution fallback (§5.3), proven first |
| Unattended first consent unsolved | One-time `doctor --grant`; upstream Mutter-direct ask |
| Consent dialog never observed rendering on the headless display (spike saw it only on the physical one) | Prove in Phase 0 before §5.5 step 2; else ship `--grant --local` |
| Cursor lag with workaround | Acceptable for desktop; gaming verified on GAME-01; labwc fallback has native cursor |
| Relative pointer (FPS games) under GNOME/libei | Phase 0 GAME-01 test; labwc fallback if it fails |
| GNOME version drift on other boxes (< 46 or newer portal behavior) | Preflight + labwc fallback |
