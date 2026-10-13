# Seat Panel Controls Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every selkies sidebar display control works on the headless GNOME seat; admin stream settings act as defaults with a bitrate cap; non-owner viewers get a "Fit to my window" takeover button.

**Architecture:** The gateway (agent/gateway.py) already swallows every `r,WxH` from viewers and drives refits for the size owner. It now also reads `scaling_dpi` from the owner's `SETTINGS,{json}`, publishes a desired GNOME logical scale to `<install>/seat-scale`, and the seat helper (seat_portal.py, on the seat's private D-Bus) applies it live through `org.gnome.Mutter.DisplayConfig.ApplyMonitorsConfig`. Viewers carry a stable per-tab id (`styx_vid`) so ownership survives refit reconnects; the gateway tells each viewer whether it owns the size (`styx-owner,1|0`) and accepts `styx-takeover`.

**Tech Stack:** Python 3.12 (aiohttp gateway, GLib/Gio seat helper on system python), vanilla JS injected shims (agent/refit.py), React admin form.

**Spec:** Decisions recorded in memory `seat-resize.md` (brainstorm + grill-me, user-confirmed 2026-10-12): seat only; HiDPI = GNOME logical scale 2 via DisplayConfig (default off); admin stream_settings = defaults, bitrate = max cap, locks only codec/use_cpu, admin changes apply on next connect; first viewer owns size, others get a Styx-injected "Fit to my window" button.

## Verified facts (from research, 2026-10-12)

- Client (selkies 2.0, WebSocket mode) sends `r,WxH,primary` on resize, preset pick, manual Apply, Reset, and HiDPI toggle. HiDPI on → size in device px; off → CSS px. Presets list includes sizes below our 640x480 clamp (fine, clamped).
- Client never sends `s,` in WebSocket mode. `scaling_dpi` arrives in every `SETTINGS,{json}` (96 when HiDPI off, the picked 96..288 stop when on).
- Server env syntax: range `"default,min-max"` (e.g. `--video-bitrate=16000,1000-16000`), single value = initial only; single-item list = lock (`--encoder=h264enc` already locks codec); `SELKIES_USE_CPU=false|locked` already locks use_cpu.
- Seat Mutter: `GetCurrentState` reports layout-mode 2 (physical), supported scales `[1.0, 2.0]`. `ApplyMonitorsConfig(serial, 1, [(0,0,2.0,0,true,[(connector, mode_id, {})])], {})` switches scale live; mode and rect unchanged (spike on an isolated headless gnome-shell).
- Admin push today (`styx_agent.py` heartbeat, `settings_restart_keys`) restarts selkies+gateway immediately → kicks viewers.

## Global Constraints

- Files < 500 lines. New agent modules MUST be added to `AGENT_UPDATE_FILES` in `backend/app/services/workstations.py` and to the `for pair in ...` list in `agent/enroll.sh`.
- `seat_portal.py` and anything it imports run on SYSTEM python (`/usr/bin/python3`, has `gi`), never the venv.
- Gateway tests that use aiohttp only run under `backend/.venv/bin/python -m pytest agent/tests`.
- Never touch the live seat, live gateway (8443) or KasmVNC (8444) from tests.
- Agent version bump to `0.7.0` (Task 6). Semantic commits, each ending with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

1. Refit reconnect must not hand ownership to a non-owner: all sockets close at once on refit; the owner returns with the same `styx_vid`.
2. Owner leaves for real (tab closed): after a grace period the newest viewer becomes owner and gets `styx-owner,1`; seat follows its size.
3. Unsupported scale (e.g. 2.0 at 640x480): DisplayConfig error is logged and ignored; the stream keeps running.
4. A resize (in-place `set_mode`) may reset the logical scale → the helper re-applies the desired scale after every resize.
5. Admin settings push while a viewer is connected must not kill the session; it applies once no viewer is connected.

---

### Task 1: Bitrate is a cap, not a lock

**Files:** Modify `agent/engine.py` (`build_selkies_cmd`, the `--video-bitrate` line); Test `agent/tests/test_engine.py`.

- [ ] Write failing test: `build_selkies_cmd` with `stream_settings={"video_bitrate_kbps": 20000}` yields `--video-bitrate=20000,1000-20000`; with no setting yields `--video-bitrate=16000,1000-16000`; with 800 (floor = `min(1000, kbps)`) yields `--video-bitrate=800,800-800`. Test all three.
- [ ] Implement: `lo = min(1000, kbps); cmd.append(f"--video-bitrate={kbps},{lo}-{kbps}")`. Replace the old "Locked server-side" comment with: `# Admin bitrate is the default AND the ceiling; viewers may lower it. Floor 1000 kbps: stale 1.x storage sends 8 (Mbps) which would otherwise mean 8 kbps.`
- [ ] Run `python3 -m pytest agent/tests/test_engine.py -q` → pass. Commit `feat(agent): admin bitrate becomes a viewer-adjustable ceiling`.

### Task 2: Admin settings push applies on next connect

**Files:** Modify `agent/styx_agent.py` (heartbeat block `if hb["stream_settings"] != cfg["stream_settings"]:`); Test `agent/tests/test_styx_agent.py`.

**Interfaces:** Produces pure helper `def viewers_connected(state_path) -> bool` (reads gateway state JSON `<install>/gw_state.json`, key `active_connections` > 0; missing/garbled file → False).

- [ ] Tests: `viewers_connected` true for `{"active_connections": 2}`, false for 0, missing file, invalid JSON.
- [ ] Implement deferral: keep writing the new settings to cfg/CONFIG_PATH immediately (as today), but put the restart (the `keys` loop + `gseat.stop()`; the seat_shell agent-exit branch too) behind a `pending_restart` variable. Each loop pass: `if pending_restart and not viewers_connected(GW_STATE): <do restart>; pending_restart = None`. Log once when deferring: `settings changed; applying when the last viewer disconnects`. When several pushes arrive while deferred, merge keys (union) and keep the earliest old settings for the `seat` comparison.
- [ ] Find the gateway state path constant already used by the agent (grep `gw_state`); reuse it.
- [ ] Note the agent loop wakes every heartbeat interval or on refit — that granularity is fine.
- [ ] Run all agent tests (both pythons). Commit `feat(agent): defer settings-push restarts until no viewer is connected`.

### Task 3: Seat logical scale (HiDPI)

**Files:** Create `agent/seat_scale.py`; modify `agent/seat_portal.py` (watch loop + after `mon.resize`), `agent/seat_gnome.py` (helper launch passes scale file path); packaging lists; Test create `agent/tests/test_seat_scale.py`.

**Interfaces:**
- Produces `scale_for_dpi(dpi) -> int`: `dpi` int/float/None → `2 if dpi and dpi >= 168 else 1` (168 = midpoint of 96 and 240; ponytail: integer scales only, Mutter offers [1.0, 2.0] without the fractional experimental feature).
- Produces `read_scale(path) -> int` (file text "1"/"2"; anything else/missing → 1) and `write_scale(path, s)` (atomic tmp+os.replace, same as `refit.write_size`).
- Produces `monitors_config(state, scale) -> tuple` pure builder: input = the unpacked Python value of `GetCurrentState` `(serial, monitors, logical_monitors, props)`; output = `(serial, 1, [(x, y, float(scale), transform, primary, [(connector, current_mode_id, {})]) for each logical monitor], {})` where `current_mode_id` is the mode with `is-current` true in that monitor's mode list; returns None if `scale` not in that mode's supported scales list (index 5 of the mode tuple) or the scale already equals the logical monitor's scale.
- Produces `apply_scale(conn, scale, log)` (Gio.DBusConnection): calls GetCurrentState, `monitors_config`, then `ApplyMonitorsConfig` with GLib.Variant `(uua(iiduba(ssa{sv}))a{sv})`. Catches GLib.Error → `log("scale", scale, "rejected:", e.message)`.
- [ ] Tests (system python is fine, pure functions only; import must not require gi at module import — import gi lazily inside `apply_scale`): `scale_for_dpi` (None→1, 96→1, 144→1, 168→2, 192→2, 288→2); `read_scale` (missing, "2", "x"); `monitors_config` with this fixture copied from a real seat:
  `(5, [(('Meta-0','MetaVendor','Virtual remote monitor','0x000001'), [('2560x1252@60.000',2560,1252,60.0,1.0,[1.0,2.0],{'is-current':True,'is-preferred':True})], {})], [(0,0,1.0,0,True,[('Meta-0','MetaVendor','Virtual remote monitor','0x000001')],{})], {'layout-mode':2})` → scale 2 gives `(5, 1, [(0,0,2.0,0,True,[('Meta-0','2560x1252@60.000',{})])], {})`; scale 1 gives None (unchanged); fixture with supported `[1.0]` and scale 2 gives None.
- [ ] seat_gnome.py: when launching the helper (`subprocess.Popen([SYS_PYTHON, str(self.install_dir / "seat_portal.py"), ...`), add arg/env so the helper knows `<install>/seat-scale` (follow how the helper already receives its other paths — e.g. the ready file; prefer an env var `STYX_SEAT_SCALE_FILE`).
- [ ] seat_portal.py: in the existing 25 ms `watch_resize` GLib timeout (or a sibling timeout at 250 ms), check the scale file's mtime; on change, `apply_scale(bus_conn, read_scale(path), log)`. After a successful `mon.resize(...)` becomes current, re-apply the desired scale. On startup (once the monitor is live), apply it too. Use the helper's existing session-bus connection.
- [ ] Packaging: add `seat_scale.py` to AGENT_UPDATE_FILES and enroll.sh pairs.
- [ ] Run tests; commit `feat(agent): seat helper applies a GNOME logical scale from <install>/seat-scale`.

### Task 4: Gateway — viewer identity, scale publishing, ownership messages, takeover

**Files:** Modify `agent/gateway.py`, `agent/refit.py` (`SizeOwner` only); Tests `agent/tests/test_gateway.py` / `test_refit.py` (follow the existing aiohttp test style there, e.g. the "all-viewer announce + handoff" test).

**Interfaces:**
- Consumes `seat_scale.scale_for_dpi`, `seat_scale.write_scale`, `seat_scale.read_scale` (Task 3).
- Wire protocol (gateway ↔ injected proxy, text frames, never forwarded upstream):
  - client → gateway query param `styx_vid=<id>` on the websocket URL (strip it before building the upstream URL).
  - gateway → client `styx-owner,1` / `styx-owner,0` (sent right after connect, and whenever ownership changes).
  - client → gateway `styx-takeover` (swallowed).
- Behaviour:
  - Owner key = `styx_vid` (fallback `id(ws_server)` when absent). `SizeOwner` keeps working with any hashable key.
  - `SETTINGS,{json}` from any viewer: parse JSON (ignore errors), remember that viewer's `scaling_dpi`. If the viewer is the owner and `scale_for_dpi(dpi) != read_scale(scale_file)`, `write_scale(scale_file, ...)`. Forward the SETTINGS upstream unchanged. `scale_file = os.path.join(seat_dir, "seat-scale")`; skip all of this when `seat_dir` is empty (mirror/labwc).
  - Ownership change (claim on first `r,`, takeover, handoff) → send `styx-owner,1` to the new owner, `styx-owner,0` to the previous one, then publish the new owner's remembered scale, then fire the new owner's refit (its last `r,` size).
  - `styx-takeover` from a non-owner: becomes owner (as above).
  - Disconnect: do NOT release ownership immediately. If the owner's vid has no live socket after `OWNER_GRACE_S = 5.0` seconds (`loop.call_later`), release and hand off to the newest viewer (existing handoff code moves into that callback). A reconnect with the same vid cancels the pending handoff and gets `styx-owner,1`.
  - Two sockets with the same vid (tab reconnecting before the old one finished closing): track live sockets per vid as a count/set; the vid is "gone" only when it has zero sockets.
- [ ] Tests (backend venv python): (a) vid query param is stripped from the upstream URL; (b) first viewer gets `styx-owner,1`, second gets `styx-owner,0`; (c) owner closes and reconnects with same vid within grace → still owner, second never receives `styx-owner,1`; (d) owner closes for good → after grace (patch `OWNER_GRACE_S` small) second gets `styx-owner,1` and a refit request to its last size is written; (e) `styx-takeover` from second → second `styx-owner,1`, first `styx-owner,0`, refit request for second's size, and `styx-takeover` is not forwarded upstream; (f) owner SETTINGS with `scaling_dpi` 192 writes `seat-scale` = "2", non-owner SETTINGS does not.
- [ ] Keep gateway.py < 500 lines: if it grows past, move the ownership bookkeeping into a small class `Viewers` in a new module `agent/viewers.py` (add to packaging lists) with methods `connect(vid, sock)`, `disconnect(vid, sock) -> bool gone`, `owner`, `newest()`.
- [ ] Commit `feat(gateway): owner-aware viewers with takeover and seat scale publishing`.

### Task 5: Injected client — vid, owner banner, "Fit to my window"

**Files:** Modify `agent/refit.py` (`_PROXY_JS`, `_WORKER_SHIM`, `_PAGE_SHIM`, `RELOAD_JS`); Tests `agent/tests/test_refit.py` + new `agent/tests/test_refit_js.py` that runs the proxy in node (skip if `shutil.which("node")` is None).

**Interfaces:** Consumes the wire protocol of Task 4.

- [ ] Proxy (`S` in `_PROXY_JS`): append `styx_vid` to the URL on every `_open` (keep existing query). The id comes from a new token `__VID__`: page side = `sessionStorage` value (create `crypto.randomUUID()` once per tab, wrapped in try/catch with a Math.random fallback); worker side = injected string literal built by the page when it rewrites the worker Blob (same place `__PAGE__` is replaced).
- [ ] Proxy `onmessage`: text `styx-owner,1|0` → do not emit to the app; call new token `OWNER(bool)` (page: `owner(on)`; worker: `self.postMessage({type:'styx-owner',on:on})`).
- [ ] Takeover path: page → worker `w.postMessage({type:'styx-takeover'})` (keep a list of wrapped workers in `SW`); worker shim listens with `self.addEventListener('message', ...)` and on that type calls the live S instance's `_ws.send('styx-takeover')` (track the latest S instance in a variable). Page-socket fallback: page calls its own latest S instance directly.
- [ ] Page UI `owner(on)`: when `on` is false show a fixed pill at top-centre (same style family as the existing "Resizing…" pill but `pointer-events:auto`, id `styx-takeover`): text `Viewing at another viewer's size` + a button `Fit to my window`. Button click → send takeover and hide the pill. When `on` is true remove it. Must be keyboard accessible (`<button>`), `aria-live="polite"` on the container.
- [ ] node test: load `_PAGE_SHIM`-equivalent proxy with a fake `WebSocket` class in a `vm` context; assert (1) the URL opened contains `styx_vid=`, (2) a `styx-owner,0` message is not delivered to `onmessage` and calls OWNER(false), (3) normal messages still delivered. Keep the harness under 80 lines.
- [ ] Commit `feat(agent): viewer id, owner banner and Fit to my window takeover`.

### Task 6: Admin form, docs, version

**Files:** `frontend/src/components/system/workstation-stream-settings.tsx`; `docs/WORKSTATIONS.md`, `docs/PERFORMANCE.md`; `agent/styx_agent.py` AGENT_VERSION → `0.7.0`; `CHANGELOG.md` only if the repo's release tooling doesn't generate it (check `release.config.js`; if semantic-release generates it, don't edit).

- [ ] Admin form: bitrate field label `Max bitrate (kbps)` with help `Viewers start here and can lower it from the stream panel.`; framerate/CRF help `Default; viewers can change it from the stream panel.`; a one-line note under the section: `Changes apply the next time nobody is connected.`
- [ ] `cd frontend && npm run build && npm test` pass.
- [ ] Docs: WORKSTATIONS.md — section "Stream panel on the GNOME seat" covering: resolution presets/manual size resize the seat; HiDPI/UI scaling map to GNOME scale 1 or 2; the first viewer owns the size, others see "Fit to my window"; admin values are defaults, bitrate is a ceiling, codec and CPU encode are locked. PERFORMANCE.md — bitrate ceiling note.
- [ ] Commit `docs: seat panel controls, admin defaults and takeover` (+ `feat(ui): ...` for the form if you prefer two commits).

### Task 7: End-to-end verification (controller does this, not a subagent)

- Isolated gateway on port 8445 (scratchpad `gw2/`), `?role=viewer` probes only against the live seat; two Playwright contexts: owner + second viewer → banner, takeover → refit; preset 1920x1080 → `seat-size` 1920x1080; HiDPI toggle with `deviceScaleFactor: 2` → `seat-scale` = 2 and DisplayConfig scale 2.0. Live-seat steps that change the user's desktop (scale, refit) need the user's go first.
