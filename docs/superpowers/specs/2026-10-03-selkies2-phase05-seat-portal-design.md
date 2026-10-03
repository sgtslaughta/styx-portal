# Selkies 2.0 Phase 0.5 — Consent-free GNOME seat, embedded cursor, size-at-connect

**Status:** approved design (2026-10-03) · **Builds on:** `2026-10-03-selkies2-gnome-seat-design.md` (Phase 0, agent 0.5.0)
**Evidence:** option-1 spike on EliteMini (AMD Radeon 780M, Ubuntu 24.04, GNOME 46), user-verified through Cloudflare.

## Goal

The headless GNOME seat must feel native through the portal: no consent dialog ever, one steady
cursor, a sharp 1:1 picture sized to the viewer's browser, and higher default quality.

## Scope

In: GNOME seat (`seat_shell == "gnome"`) only. Agent → 0.6.0 (minor: new behaviour, removed `doctor --grant`).
Out: labwc seat and mirror mode (unchanged); mid-session live resize; a fit-to-window button or
shortcut (user chose **reconnect only** — reload the page to refit); WebRTC/TURN; audio changes.

## Spike findings this design relies on

1. A private xdg-desktop-portal backend implementing `org.freedesktop.impl.portal.ScreenCast` and
   `.RemoteDesktop` on Mutter's own `org.gnome.Mutter.ScreenCast` / `.RemoteDesktop` D-Bus APIs needs
   no consent and gives pixelflux a working stream + libei input. It is selected with
   `XDG_DESKTOP_PORTAL_DIR=<dir>` where `<dir>` holds our `styx.portal`, copies of the system
   `*.portal` files, and `portals.conf` / `ubuntu-portals.conf` / `gnome-portals.conf` routing
   ScreenCast + RemoteDesktop to `styx` (the frontend reads `portals.conf` from that dir).
2. dbus-python resolves a method by Python attribute name along the MRO; ScreenCast and
   RemoteDesktop share member names (`CreateSession`, `Start`), so each interface's methods live on
   a separate class level (RemoteDesktop on the subclass, ScreenCast on its parent). Notify* methods
   need fixed arity (no `*args`).
3. Cursor: Mutter cursor-mode **embedded (1)** + selkies `--enable-cursors=false` + gateway
   `CURSOR_HIDE_CSS` → no flicker, acceptable lag. Metadata (2) and `--use-browser-cursors` flicker.
4. A `RecordVirtual({'is-platform': True})` monitor held by a GStreamer consumer
   (`pipewiresrc ! capsfilter(video/x-raw,width=W,height=H,max-framerate=60/1) ! fakesink`) gives
   GNOME a WxH monitor. **In-place resize (caps renegotiation) stalls frames** and is not used.
   A fresh monitor at WxH followed by a fresh selkies is reliable. Removing the monitor under a
   running selkies crashes selkies → selkies must be stopped first.
5. The client's size request is the WS text message `r,<W>x<H>,<displayId>` (e.g.
   `r,2552x1294,primary`); selkies checks the host size immediately on receipt.
6. Edge cannot decode H.265; a client choosing AV1/H.265 shows a black stream. `--encoder=h264enc`
   (single value) restricts the client to H.264. The log line
   `No usable encoding entrypoint found for profile VAProfileH264High` is benign on radeonsi.

## Components

| Unit | Responsibility |
|---|---|
| `agent/seat_portal.py` (new, < 300 lines) | One process on the seat's private bus. (a) Portal backend on bus name `org.freedesktop.impl.portal.desktop.styx`, object `/org/freedesktop/portal/desktop`: ScreenCast (`AvailableSourceTypes=1`, `AvailableCursorModes=7`, `version=5`) + RemoteDesktop (`AvailableDeviceTypes=3`, `version=2`); `Start` creates a Mutter RD session + linked ScreenCast session, `RecordMonitor("", cursor-mode=1)` **always embedded**, replies with streams/devices on `PipeWireStreamAdded`; `ConnectToEIS` forwards Mutter's fd; Notify* forward. (b) Holds the virtual monitor at the `WxH` given as `argv[1]`. Prints `ready WxH` once the consumer is playing. |
| `agent/portals/` (new dir, shipped in the agent tarball) | `styx.portal` + `portals.conf`, `ubuntu-portals.conf`, `gnome-portals.conf`. System `*.portal` files are copied in at seat start (they vary by distro). |
| `agent/refit.py` (new, small, pure) | `clamp(w, h)` → even dims within 640×480 … 3840×2160. `decide(req, current, last_refit_ts, now)` → target `(w, h)` or `None`: `None` when both dims are within 16 px of current, or a refit happened < 10 s ago. `parse_resize(msg)` → `(w, h)` from `r,WxH[,id]` or `None`. |
| `agent/seat_gnome.py` | Launch GNOME **without** `--virtual-monitor`; launch script exports `XDG_DESKTOP_PORTAL_DIR`, starts `seat_portal.py WxH` in the session before anything activates a portal. New `refit(w, h)`: restart the helper, wait (≤ 10 s) until `DisplayConfig.GetCurrentState` reports WxH. Remove `TOKEN_PATH`, `needs_consent`, `CONSENT_ERROR`, `Escalation`. |
| `agent/gateway.py` | Per WS connection, on the **first** client `r,` message: `refit.decide`; if a target is returned, write `want_size: "WxH"` to gw-state and close the client socket with code **4002** (message `refit`), without forwarding. Later `r,` messages pass through unchanged (selkies letterboxes). |
| `agent/styx_agent.py` | Supervisor loop: on `want_size` in gw-state (and it differs from the current size), stop selkies → `seat.refit(w, h)` → persist size to `<install>/seat-size` → start selkies → clear `want_size`. Seat starts at the persisted size, else `seat_width × seat_height` from settings. Remove `doctor --grant` and consent handling. |
| `agent/engine.py` | GNOME seat branch always emits `--enable-cursors=false`. Quality defaults (all seats/modes, overridable per workstation as today): bitrate `16000` kbps locked (`--video-bitrate=16000-16000` when unset), `--video-max-qp=28`, `--use-paint-over-quality=true`, `--video-paintover-crf=16`, `--encoder=h264enc`, framerate 60. |
| Removed | `agent/grant.py`, its tests, the `doctor --grant` advisory in `health.py`, the `cursor_workaround` setting (agent env `STYX_GW_CURSOR_WORKAROUND`, backend `WORKSTATION_CURSOR_WORKAROUND`, settings spec, `ws_settings`). The gateway always hides the cursor on a GNOME seat. |

`styx_agent.py` (499 lines) and `gateway.py` (459) are at the 500-line ceiling: new logic goes in
`refit.py` / `seat_portal.py`; removals in `styx_agent.py` must offset additions.

## Data flow (connect)

1. Browser opens the workstation URL; gateway proxies; client sends `r,2552x1294,primary`.
2. Gateway: monitor is 1920×1080 → `decide` returns `(2552, 1294)` → gw-state `want_size`, close 4002.
3. Agent: stop selkies → restart `seat_portal.py 2552x1294` → wait for Mutter WxH → persist → start selkies.
4. Client reconnects (or the injected reload shim reloads the page on close code 4002 — see Risks),
   sends the same size, `decide` → `None`, stream runs 1:1.

Mid-session browser resize: no refit; selkies letterboxes. Reload to refit.

## Error handling

- Refit timeout (10 s) or helper exit → restart helper at the **previous** size, start selkies,
  record advisory `refit failed: <reason>` in heartbeat info. No retry until the next connect.
- Helper crash while running → existing seat health check restarts the seat helper at the persisted size.
- Invalid / absurd `r,` values → `clamp`; non-matching messages are forwarded untouched.
- Refit storm (many tabs/reloads) → 10 s rate limit in `decide`.

## Risks / verify first in the plan

1. Whether the selkies 2.0 client reconnects by itself after close code 4002. If not, the gateway
   injects a ~5-line shim: on WS close with code 4002, `location.reload()` once.
2. `python3-dbus`, `python3-gi`, GStreamer `pipewiresrc` (`gstreamer1.0-pipewire`) must exist on
   the box. Enroll preflight checks them; per the no-remote-toolchains rule, `--upgrade` never installs.
3. A refit moves GNOME windows onto the new monitor; acceptable (windows survive).

## Testing

- Unit: `refit` (clamp bounds, even dims, 16 px tolerance, 10 s rate limit, `parse_resize` with/without id, garbage);
  engine flags (cursor off on GNOME seat, quality defaults, per-WS bitrate override still wins);
  gateway (fake upstream: first `r,` mismatch → no forward + close 4002 + gw-state `want_size`;
  match → forwarded; second `r,` forwarded);
  `seat_portal` method tables (ScreenCast vs RemoteDesktop on separate class levels, signatures) without a bus;
  backend: `cursor_workaround` gone from effective settings and settings spec.
- Live on EliteMini via Cloudflare: no dialog after a clean seat start; one steady cursor;
  reload at a new window size → 1:1 within ~3 s and open windows preserved; text sharp.

## Rollout

Branch `feat/selkies2-phase05-seat-portal` → agent 0.6.0 → merge → `enroll.sh --upgrade` on EliteMini.
GAME-01 when online. Production token issue disappears (no consent path remains).
