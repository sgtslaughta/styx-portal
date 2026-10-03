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
| `agent/seat_portal.py` (new, < 300 lines) | One process on the seat's private bus. (a) Portal backend on bus name `org.freedesktop.impl.portal.desktop.styx`, object `/org/freedesktop/portal/desktop`: ScreenCast (`AvailableSourceTypes=1`, `AvailableCursorModes=7`, `version=5`) + RemoteDesktop (`AvailableDeviceTypes=3`, `version=2`); `Start` creates a Mutter RD session + linked ScreenCast session, `RecordMonitor("", cursor-mode=1)` **always embedded**, replies with streams/devices on `PipeWireStreamAdded`; `ConnectToEIS` forwards Mutter's fd; Notify* forward. (b) Holds the virtual monitor at the `WxH` given as `argv[1]`. (c) Once Mutter reports that monitor current at WxH, starts `xdg-desktop-portal --replace` (reads `XDG_DESKTOP_PORTAL_DIR`) and writes `WxH` to `$STYX_PORTAL_READY`. Runs with the **system** `/usr/bin/python3`. `--selftest` checks the method tables without a bus. |
| `seat_gnome.write_portal_dir()` | Generates `<install>/portals/` at seat start: copies of `/usr/share/xdg-desktop-portal/portals/*.portal`, our `styx.portal`, and `portals.conf` / `ubuntu-portals.conf` / `gnome-portals.conf` (content verbatim from the spike). |
| `agent/refit.py` (new, small, pure) | `clamp(w, h)` → even dims within 640×480 … 3840×2160. `decide(req, current, last_refit_ts, now)` → target `(w, h)` or `None`: `None` when both dims are within 16 px of current, or a refit happened < 10 s ago. `parse_resize(msg)` → `(w, h)` from `r,WxH[,id]` or `None`. |
| `agent/seat_gnome.py` | Launch GNOME **without** `--virtual-monitor`; launch script puts `XDG_DESKTOP_PORTAL_DIR` in the activation env. `ready()` starts the helper once the shell answers and waits (≤ 10 s) for its ready file. New `refit(w, h) -> bool`: restart the helper at WxH, on failure restart it at the previous size. Persists the live size to `<install>/seat-size`. `gnome_available()` also checks `python3 -c 'import dbus, gi'` and `gst-inspect-1.0 pipewiresrc` (missing → labwc fallback with reason). Remove `TOKEN_PATH`, `needs_consent`, `CONSENT_ERROR`, `CONSENT_PENDING_S`. `Escalation` stays (general wedge recovery). |
| `agent/gateway.py` | Enabled when `STYX_GW_SEAT_DIR` is set (GNOME seat). Per WS connection, on the **first** client `r,` message: `refit.decide` against `<seat_dir>/seat-size`; if a target is returned, `refit.request()` writes `<seat_dir>/refit-request` and the client socket is closed with code **4002** without forwarding. Later `r,` messages pass through (selkies letterboxes). `index` returns 503 while `refit-request` exists. A reload shim is injected: on WS close 4002 it polls the page until 200, then `location.reload()`. Cursor-hide CSS is always injected on the GNOME seat. |
| `agent/styx_agent.py` | Loop sleep becomes `refit.wait_for_request(<install>/refit-request, interval)`; on a request: stop selkies → `gseat.refit(w, h)` → `refit.clear_request()` → loop restarts selkies. Seat starts at the persisted size, else `seat_width × seat_height`. Remove `doctor --grant` and consent handling. Gateway env `STYX_GW_CURSOR_WORKAROUND` replaced by `STYX_GW_SEAT_DIR`. |
| `agent/engine.py` | GNOME seat branch always emits `--enable-cursors=false`. Quality defaults (all seats/modes, overridable per workstation as today): bitrate `16000` kbps locked (`--video-bitrate=16000-16000` when unset), `--video-max-qp=28`, `--use-paint-over-quality=true`, `--video-paintover-crf=16`, `--encoder=h264enc`, framerate 60. |
| `agent/refit.py` file protocol | `read_size(path)`, `write_size(path, w, h)`, `request(path, w, h)` (atomic), `pending(path)`, `clear_request(path)`, `wait_for_request(path, timeout, poll=0.25)`. |
| Removed | `agent/grant.py`, its tests, the `doctor --grant` advisory in `health.py`, the `cursor_workaround` setting (agent env `STYX_GW_CURSOR_WORKAROUND`, backend `WORKSTATION_CURSOR_WORKAROUND`, settings spec, `ws_settings`). The gateway always hides the cursor on a GNOME seat. |

`styx_agent.py` (499 lines) and `gateway.py` (459) are at the 500-line ceiling: new logic goes in
`refit.py` / `seat_portal.py`; removals in `styx_agent.py` must offset additions.

## Data flow (connect)

1. Browser opens the workstation URL; gateway proxies; client sends `r,2552x1294,primary`.
2. Gateway: `seat-size` is 1920×1080 → `decide` returns `(2552, 1294)` → writes `refit-request`, closes 4002.
3. Shim polls the page (503 while the request file exists). Agent wakes (≤ 0.25 s): stop selkies →
   restart `seat_portal.py 2552x1294` → helper ready → `seat-size` updated → request cleared → start selkies.
4. Shim sees 200 → reload → client sends the same size → `decide` → `None` → stream runs 1:1.
   If selkies is not up yet, the gateway's existing 502 path and the client's retry cover the gap.

Mid-session browser resize: no refit; selkies letterboxes. Reload to refit.

## Error handling

- Refit timeout (10 s) or helper exit → restart helper at the **previous** size, start selkies,
  record advisory `refit failed: <reason>` in heartbeat info. No retry until the next connect.
- Helper crash while running → existing seat health check restarts the seat helper at the persisted size.
- Invalid / absurd `r,` values → `clamp`; non-matching messages are forwarded untouched.
- Refit storm (many tabs/reloads) → 10 s rate limit in `decide`.

## Risks / verify first in the plan

1. The reload shim wraps `window.WebSocket`; verify the selkies 2.0 client still connects through it.
2. `python3-dbus`, `python3-gi`, GStreamer `pipewiresrc` (`gstreamer1.0-pipewire`) must exist on
   the box. Checked at runtime by `gnome_available()` (labwc fallback); never installed remotely.
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
