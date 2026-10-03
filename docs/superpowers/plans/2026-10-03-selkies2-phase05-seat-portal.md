# Selkies 2.0 Phase 0.5 — Consent-free GNOME Seat Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** GNOME seat with no consent dialog, one steady embedded cursor, a virtual monitor sized to the viewer's browser at connect, and higher default quality (agent 0.6.0).

**Architecture:** A new system-python helper (`agent/seat_portal.py`) runs on the seat's private D-Bus as both an auto-approving xdg-desktop-portal backend (built on Mutter's own ScreenCast/RemoteDesktop APIs) and the holder of the seat's virtual monitor. The gateway catches the browser's first `r,WxH` message, drops a request file and closes the socket (4002); the agent restarts the helper at the new size and restarts selkies; an injected shim reloads the page. Pure size/file logic lives in `agent/refit.py`.

**Tech Stack:** Python 3.12 (agent venv: aiohttp), system python3 (dbus-python, PyGObject, GStreamer `pipewiresrc`), selkies 2.0.0 / pixelflux 2.1.0, FastAPI backend, pytest.

**Spec:** `docs/superpowers/specs/2026-10-03-selkies2-phase05-seat-portal-design.md`

## Global Constraints

- Branch: `feat/selkies2-phase05-seat-portal` (already checked out in `/home/user/code/remote-access`).
- Agent tests: `cd /home/user/code/remote-access/agent && ../backend/.venv/bin/python -m pytest -q tests` (baseline: 151 passed, 1 skipped).
- Backend tests: `cd /home/user/code/remote-access/backend && .venv/bin/python -m pytest -q`; lint: `.venv/bin/python -m ruff check app/ tests/`.
- Every Python file stays ≤ 500 lines (`agent/styx_agent.py` is at 499 and `agent/gateway.py` at 459 before this plan — check with `wc -l`).
- Semantic commits (`feat(agent): …`, `fix: …`, `refactor: …`, `test: …`), each ending with the line `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Scope is the GNOME seat only; labwc seat and mirror mode behaviour must not change (except the quality defaults in Task 2, which apply to all modes).
- Size limits: clamp 640×480 … 3840×2160, even dims, tolerance 16 px, refit rate limit 10 s, helper ready timeout 10 s, close code 4002.
- Quality defaults: `--video-bitrate=16000-16000` (per-workstation `video_bitrate_kbps` still wins), `--video-max-qp=28`, paint-over on, paint-over CRF 16, `--encoder=h264enc`, framerate 60.
- Never install packages on the box (no apt in code paths); missing helper deps → labwc fallback with a reason.
- Mutter cursor-mode: 0 hidden, 1 embedded, 2 metadata. The seat always uses **1**.

## Review Focus

1. A garbage or unparsable `refit-request` file (partial write, manual edit) → it is cleared, so the gateway never answers 503 forever. (Task 1 test `test_wait_for_request_clears_garbage`.)
2. A browser at an absurd size (320×200 phone, 7680×4320 8K) → refit clamps to 640×480 / 3840×2160, never asks Mutter for an impossible monitor. (Task 1 test `test_clamp_bounds_and_even`.)
3. Two tabs at different sizes connecting back-to-back → the 10 s rate limit stops them refitting each other in a loop. (Task 1 test `test_decide_rate_limited`, Task 5 test `test_second_resize_in_window_is_forwarded`.)
4. The helper fails to come up at the new size → the seat goes back to the previous size instead of being left monitorless. (Task 4 test `test_refit_failure_restores_previous_size`.)
5. A settings DB that still holds the removed `WORKSTATION_CURSOR_WORKAROUND` row → settings load and the heartbeat keep working. (Task 7 test `test_removed_cursor_setting_row_is_ignored`.)

---

### Task 1: `agent/refit.py` — size rules, request-file protocol, reload shim

**Files:**
- Create: `agent/refit.py`
- Test: `agent/tests/test_refit.py`

**Interfaces:**
- Produces (used by Tasks 4, 5, 6):
  - `CLOSE_CODE: int = 4002`
  - `clamp(w: int, h: int) -> tuple[int, int]`
  - `parse_resize(msg) -> tuple[int, int] | None`
  - `decide(req: tuple[int, int], current: tuple[int, int] | None, last_refit_ts: float, now: float) -> tuple[int, int] | None`
  - `read_size(path) -> tuple[int, int] | None`, `write_size(path, w, h) -> None`, `request(path, w, h) -> None`, `pending(path) -> bool`, `clear_request(path) -> None`
  - `wait_for_request(path, timeout: float, poll: float = 0.25, sleep=time.sleep, clock=time.monotonic) -> tuple[int, int] | None`
  - `inject_reload(html: str, enabled: bool) -> str` (adds `<script id="styx-refit">` before `</head>`)

- [ ] **Step 1: Write the failing tests** — create `agent/tests/test_refit.py`:

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import refit  # noqa: E402


def test_clamp_bounds_and_even():
    assert refit.clamp(320, 200) == (640, 480)
    assert refit.clamp(7680, 4320) == (3840, 2160)
    assert refit.clamp(2553, 1295) == (2552, 1294)


def test_parse_resize():
    assert refit.parse_resize("r,2552x1294,primary") == (2552, 1294)
    assert refit.parse_resize("r,1920x1080") == (1920, 1080)
    for bad in ("r,1920,1080", "r,axb", "kd,65", "r,99999999x1", b"r,1x1", None):
        assert refit.parse_resize(bad) is None


def test_decide_tolerance_and_unknown_current():
    assert refit.decide((2560, 1300), (2552, 1294), 0, 100) is None      # within 16 px
    assert refit.decide((2552, 1294), (1920, 1080), 0, 100) == (2552, 1294)
    assert refit.decide((2552, 1294), None, 0, 100) == (2552, 1294)       # no seat-size yet
    assert refit.decide((100, 100), (640, 480), 0, 100) is None           # clamps to current


def test_decide_rate_limited():
    assert refit.decide((2552, 1294), (1920, 1080), 95, 100) is None      # 5 s after last
    assert refit.decide((2552, 1294), (1920, 1080), 89, 100) == (2552, 1294)


def test_size_file_roundtrip_and_request(tmp_path):
    f = tmp_path / "seat-size"
    assert refit.read_size(f) is None
    refit.write_size(f, 2552, 1294)
    assert refit.read_size(f) == (2552, 1294)
    r = tmp_path / "refit-request"
    assert not refit.pending(r)
    refit.request(r, 1920, 1080)
    assert refit.pending(r) and refit.read_size(r) == (1920, 1080)
    refit.clear_request(r)
    refit.clear_request(r)                                              # idempotent
    assert not refit.pending(r)


def test_wait_for_request_returns_request_or_times_out(tmp_path):
    r = tmp_path / "refit-request"
    t = {"now": 0.0}
    clock = lambda: t["now"]                                            # noqa: E731

    def sleep(s):
        t["now"] += s
    assert refit.wait_for_request(r, 1.0, sleep=sleep, clock=clock) is None
    assert t["now"] >= 1.0
    refit.request(r, 1920, 1080)
    assert refit.wait_for_request(r, 1.0, sleep=sleep, clock=clock) == (1920, 1080)


def test_wait_for_request_clears_garbage(tmp_path):
    r = tmp_path / "refit-request"
    r.write_text("garbage")
    t = {"now": 0.0}
    assert refit.wait_for_request(r, 0.5, sleep=lambda s: t.update(now=t["now"] + s),
                                  clock=lambda: t["now"]) is None
    assert not r.exists()


def test_inject_reload():
    html = "<html><head></head><body></body></html>"
    out = refit.inject_reload(html, True)
    assert 'id="styx-refit"' in out and "4002" in out and out.index("styx-refit") < out.index("</head>")
    assert refit.inject_reload(html, False) == html
    assert refit.inject_reload("<p>no head</p>", True) == "<p>no head</p>"
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd /home/user/code/remote-access/agent && ../backend/.venv/bin/python -m pytest -q tests/test_refit.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'refit'`

- [ ] **Step 3: Implement** — create `agent/refit.py`:

```python
"""Size-at-connect refit for the headless GNOME seat (spec: phase 0.5).

The gateway sees the browser's first `r,WxH[,display]` message. If it differs
from the live seat size (<install>/seat-size) it writes <install>/refit-request
and closes the socket with CLOSE_CODE; the agent rebuilds the virtual monitor at
that size, then clears the request. The injected shim reloads the page once the
gateway serves it again (503 while a request is pending). Pure helpers only."""
import os
import re
import time
from pathlib import Path

CLOSE_CODE = 4002
MIN_W, MIN_H, MAX_W, MAX_H = 640, 480, 3840, 2160
TOLERANCE_PX = 16
MIN_INTERVAL_S = 10.0
_RESIZE = re.compile(r"r,(\d{1,5})x(\d{1,5})(?:,.*)?")
_SIZE = re.compile(r"(\d{1,5})x(\d{1,5})")

RELOAD_JS = (
    '<script id="styx-refit">(function(){var W=window.WebSocket;'
    "function S(u,p){var s=p===undefined?new W(u):new W(u,p);"
    "s.addEventListener('close',function(e){if(e.code!==4002)return;var n=0;"
    "(function poll(){fetch(location.href,{cache:'no-store'}).then(function(r){"
    "if(r.ok)location.reload();else throw 0}).catch(function(){if(++n<60)"
    "setTimeout(poll,500)})})()});return s}"
    "S.prototype=W.prototype;['CONNECTING','OPEN','CLOSING','CLOSED'].forEach("
    "function(k){S[k]=W[k]});window.WebSocket=S})();</script>")


def clamp(w: int, h: int) -> tuple[int, int]:
    w = min(max(w, MIN_W), MAX_W)
    h = min(max(h, MIN_H), MAX_H)
    return w // 2 * 2, h // 2 * 2


def parse_resize(msg) -> tuple[int, int] | None:
    if not isinstance(msg, str):
        return None
    m = _RESIZE.fullmatch(msg)
    return (int(m[1]), int(m[2])) if m else None


def decide(req, current, last_refit_ts: float, now: float):
    """Target size for a refit, or None (close enough, or refitted < 10 s ago)."""
    w, h = clamp(*req)
    if current and abs(w - current[0]) <= TOLERANCE_PX and abs(h - current[1]) <= TOLERANCE_PX:
        return None
    if now - last_refit_ts < MIN_INTERVAL_S:
        return None
    return w, h


def read_size(path) -> tuple[int, int] | None:
    try:
        m = _SIZE.fullmatch(Path(path).read_text().strip())
    except OSError:
        return None
    return (int(m[1]), int(m[2])) if m else None


def write_size(path, w: int, h: int) -> None:
    p = Path(path)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(f"{w}x{h}")
    os.replace(tmp, p)


def request(path, w: int, h: int) -> None:
    write_size(path, w, h)


def pending(path) -> bool:
    return Path(path).exists()


def clear_request(path) -> None:
    Path(path).unlink(missing_ok=True)


def wait_for_request(path, timeout: float, poll: float = 0.25,
                     sleep=time.sleep, clock=time.monotonic):
    """Sleep up to `timeout`, returning early with a pending request's size.
    An unparsable request file is cleared (else the gateway 503s forever)."""
    end = clock() + timeout
    while True:
        req = read_size(path)
        if req:
            return req
        if pending(path):
            clear_request(path)
        left = end - clock()
        if left <= 0:
            return None
        sleep(min(poll, left))


def inject_reload(html: str, enabled: bool) -> str:
    if not enabled or "</head>" not in html:
        return html
    return html.replace("</head>", RELOAD_JS + "</head>", 1)
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd /home/user/code/remote-access/agent && ../backend/.venv/bin/python -m pytest -q tests/test_refit.py`
Expected: 8 passed

- [ ] **Step 5: Commit**

```bash
cd /home/user/code/remote-access
git add agent/refit.py agent/tests/test_refit.py
git commit -m "feat(agent): refit helpers for size-at-connect GNOME seat

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: `agent/engine.py` — embedded cursor always on GNOME seat, quality defaults

**Files:**
- Modify: `agent/engine.py` (seat branch near line 219; quality block near lines 240–258)
- Test: `agent/tests/test_engine.py` (tests `test_quality_env_ignores_bad_values`, `test_bitrate_locked_server_side`, `test_gnome_cursor_workaround_disables_client_cursor`)

**Interfaces:**
- Consumes: nothing new. `build_selkies_cmd(cfg, internal_port, seat=None)` signature unchanged.
- Produces: GNOME-seat command always contains `--enable-cursors=false`; all modes get `--video-max-qp=28`, `SELKIES_USE_PAINT_OVER_QUALITY=true`, `SELKIES_VIDEO_PAINTOVER_CRF=16` defaults, bitrate default 16000.

- [ ] **Step 1: Update the tests first.** In `agent/tests/test_engine.py`:

Replace the last two lines of `test_quality_env_ignores_bad_values` body:

```python
    assert "SELKIES_VIDEO_CRF" not in env
    assert env["SELKIES_VIDEO_PAINTOVER_CRF"] == "16"          # bad value -> default
    assert env["SELKIES_VIDEO_STREAMING_MODE"] == "false"   # 2.0 default is true; keep ours
```

In `test_bitrate_locked_server_side` change both `"--video-bitrate=8000-8000"` to `"--video-bitrate=16000-16000"`.

Replace `test_gnome_cursor_workaround_disables_client_cursor` entirely with:

```python
def test_gnome_seat_always_disables_client_cursor(tmp_path, monkeypatch):
    """The seat portal embeds the cursor in the frames; a client-drawn cursor on
    top doubles/flickers. labwc forwards real cursor metadata, so it keeps it."""
    seat = {"socket": "s", "bus": "b"}
    assert "--enable-cursors=false" in _seat_cmd(tmp_path, monkeypatch, {}, seat)
    assert "--enable-cursors=false" not in _seat_cmd(tmp_path, monkeypatch, {})


def test_quality_defaults(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, stream_settings={})
    _stub(monkeypatch)
    cmd, env = engine.build_selkies_cmd(cfg, 1)
    assert "--video-max-qp=28" in cmd and "--encoder=h264enc" in cmd
    assert env["SELKIES_USE_PAINT_OVER_QUALITY"] == "true"
    assert env["SELKIES_VIDEO_PAINTOVER_CRF"] == "16"
    _, env = engine.build_selkies_cmd(
        _cfg(tmp_path, stream_settings={"use_paint_over_quality": False}), 1)
    assert env["SELKIES_USE_PAINT_OVER_QUALITY"] == "false"
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd /home/user/code/remote-access/agent && ../backend/.venv/bin/python -m pytest -q tests/test_engine.py`
Expected: FAIL in `test_quality_env_ignores_bad_values`, `test_bitrate_locked_server_side`, `test_gnome_seat_always_disables_client_cursor`, `test_quality_defaults`.

- [ ] **Step 3: Implement** in `agent/engine.py`.

Replace:

```python
        if s.get("cursor_workaround"):
            # Portal capture bakes the cursor into the video; a client-drawn
            # cursor on top doubles it (flicker, stale cursor on leave).
            cmd.append("--enable-cursors=false")
```

with:

```python
        # The seat portal embeds the cursor in the frames (metadata cursors
        # flicker); a client-drawn cursor on top would double it.
        cmd.append("--enable-cursors=false")
```

Replace the block from `kbps = _int_in(s.get("video_bitrate_kbps"), 500, 200000) or 8000` through the `SELKIES_VIDEO_PAINTOVER_CRF` assignment with:

```python
    kbps = _int_in(s.get("video_bitrate_kbps"), 500, 200000) or 16000
    cmd.append(f"--video-bitrate={kbps}-{kbps}")
    # Caps compression under motion so screen text stays legible.
    cmd.append("--video-max-qp=28")
    env["SELKIES_USE_PAINT_OVER_QUALITY"] = (
        "false" if s.get("use_paint_over_quality") is False else "true")
    pcrf = _int_in(s.get("video_paintover_crf", s.get("h264_paintover_crf")), 5, 50)
    env["SELKIES_VIDEO_PAINTOVER_CRF"] = str(16 if pcrf is None else pcrf)
```

- [ ] **Step 4: Run all agent tests**

Run: `cd /home/user/code/remote-access/agent && ../backend/.venv/bin/python -m pytest -q tests`
Expected: all pass (the 151 baseline + new ones; `test_quality_env_prefers_video_keys_and_keeps_old` still sees `"18"`).

- [ ] **Step 5: Commit**

```bash
cd /home/user/code/remote-access
git add agent/engine.py agent/tests/test_engine.py
git commit -m "feat(agent): embedded cursor on GNOME seat and higher quality defaults

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: `agent/seat_portal.py` — consent-free portal backend + virtual monitor helper

**Files:**
- Create: `agent/seat_portal.py` (< 300 lines; runs under the SYSTEM `/usr/bin/python3`, never the agent venv)
- Test: `agent/tests/test_seat_portal.py`

**Interfaces:**
- Consumes: env `DBUS_SESSION_BUS_ADDRESS` (seat bus), `XDG_DESKTOP_PORTAL_DIR` (read by the frontend it spawns), `STYX_PORTAL_READY` (ready-file path); `argv[1]` = `WxH` or `--selftest`.
- Produces (used by Task 4): process that, once Mutter reports the virtual monitor current at WxH, starts `xdg-desktop-portal --replace` and atomically writes `WxH` to `$STYX_PORTAL_READY`; exits 0 on SIGTERM (removes the ready file), 1 if the monitor never comes up within 10 s. `selftest() -> int` returns 0.

Background (do not skip): this code was proven in a throwaway spike. Two dbus-python rules matter:
(1) dbus-python resolves an incoming call by the Python attribute name equal to the D-Bus member name, walking the MRO and skipping entries whose interface differs. ScreenCast and RemoteDesktop both have `CreateSession` and `Start`, so the ScreenCast methods live on a parent class (`ScreenCastLevel`) and the RemoteDesktop methods on its subclass (`Seat`), built with `type()`.
(2) Methods need real functions with fixed arity (no lambdas, no `*args`) because dbus-python inspects the argspec.

- [ ] **Step 1: Write the failing test** — create `agent/tests/test_seat_portal.py`:

```python
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
try:
    import seat_portal  # needs system dbus-python + PyGObject + Gst typelib
except (ImportError, ValueError):
    pytest.skip("seat_portal needs dbus-python/PyGObject/Gst", allow_module_level=True)


def test_selftest_method_tables():
    assert seat_portal.selftest() == 0


def test_parse_size():
    assert seat_portal.parse_size("2552x1294") == (2552, 1294)
    for bad in ("0x10", "axb", "1920"):
        with pytest.raises(ValueError):
            seat_portal.parse_size(bad)
```

Note: the backend venv has no dbus-python, so this module SKIPS there. The real check is Step 4's system-python run.

- [ ] **Step 2: Run to verify it fails**

Run: `cd /home/user/code/remote-access/agent && /usr/bin/python3 seat_portal.py --selftest`
Expected: `can't open file ... seat_portal.py: [Errno 2] No such file or directory`

- [ ] **Step 3: Implement** — create `agent/seat_portal.py`:

```python
"""Styx GNOME seat helper (runs with the SYSTEM python3: dbus-python, PyGObject
and GStreamer's pipewiresrc). Only ever run on the seat's private session bus.

1. Portal backend `org.freedesktop.impl.portal.desktop.styx`: ScreenCast and
   RemoteDesktop implemented on Mutter's own D-Bus APIs, so there is no consent
   dialog. The cursor is always embedded in the frames (metadata cursors flicker).
2. Holds the seat's virtual monitor at WxH (argv[1]) via Mutter RecordVirtual
   plus a fakesink consumer whose caps fix the size. A new size means a new
   process: renegotiating caps in place stalls frames.
3. Once Mutter reports that monitor current, starts xdg-desktop-portal
   --replace (it reads XDG_DESKTOP_PORTAL_DIR) and writes WxH to
   $STYX_PORTAL_READY."""
import os
import signal
import subprocess
import sys

import dbus
import dbus.service
import gi
from dbus.mainloop.glib import DBusGMainLoop

gi.require_version("Gst", "1.0")
from gi.repository import GLib, Gst  # noqa: E402

BUS_NAME = "org.freedesktop.impl.portal.desktop.styx"
PATH = "/org/freedesktop/portal/desktop"
SC_IFACE = "org.freedesktop.impl.portal.ScreenCast"
RD_IFACE = "org.freedesktop.impl.portal.RemoteDesktop"
SESS_IFACE = "org.freedesktop.impl.portal.Session"
M = "org.gnome.Mutter."
EMBEDDED = 1            # Mutter cursor-mode: 0 hidden, 1 embedded, 2 metadata
FRONTENDS = ("/usr/libexec/xdg-desktop-portal", "/usr/lib/xdg-desktop-portal")
LIVE_TRIES = 50         # x 200 ms = 10 s for the monitor to come up

bus = None              # set in main(); classes only touch it at call time
sessions = {}


def log(*a):
    print("[seat-portal]", *a, flush=True)


def parse_size(arg: str) -> tuple[int, int]:
    w, h = (int(v) for v in arg.lower().split("x"))
    if w <= 0 or h <= 0:
        raise ValueError(arg)
    return w, h


def _mutter(name, path, iface):
    return dbus.Interface(bus.get_object(M + name, path), M + iface)


class Session(dbus.service.Object):
    def __init__(self, handle):
        super().__init__(bus, handle)
        self.handle = str(handle)
        self.rd = self.rd_path = self.stream_path = None
        self.devices = 3
        self.want_screen = True

    @dbus.service.method(SESS_IFACE)
    def Close(self):
        log("Close", self.handle)
        try:
            if self.rd is not None:
                self.rd.Stop()
        except dbus.DBusException as e:
            log("stop failed:", e)
        sessions.pop(self.handle, None)
        self.remove_from_connection()

    @dbus.service.signal(SESS_IFACE)
    def Closed(self):
        pass


class Portal(dbus.service.Object):
    def __init__(self):
        super().__init__(bus, PATH)

    @dbus.service.method(dbus.PROPERTIES_IFACE, in_signature="ss", out_signature="v")
    def Get(self, iface, prop):
        return self.GetAll(iface)[prop]

    @dbus.service.method(dbus.PROPERTIES_IFACE, in_signature="s", out_signature="a{sv}")
    def GetAll(self, iface):
        if iface == SC_IFACE:
            return {"AvailableSourceTypes": dbus.UInt32(1),
                    "AvailableCursorModes": dbus.UInt32(7), "version": dbus.UInt32(5)}
        if iface == RD_IFACE:
            return {"AvailableDeviceTypes": dbus.UInt32(3), "version": dbus.UInt32(2)}
        return {}

    def _start(self, s, ok):
        try:
            if s.rd is None:
                s.rd_path = _mutter("RemoteDesktop", "/org/gnome/Mutter/RemoteDesktop",
                                    "RemoteDesktop").CreateSession()
                s.rd = _mutter("RemoteDesktop", s.rd_path, "RemoteDesktop.Session")
            if s.want_screen:
                sid = dbus.Interface(bus.get_object(M + "RemoteDesktop", s.rd_path),
                                     dbus.PROPERTIES_IFACE).Get(
                    M + "RemoteDesktop.Session", "SessionId")
                scp = _mutter("ScreenCast", "/org/gnome/Mutter/ScreenCast",
                              "ScreenCast").CreateSession({"remote-desktop-session-id": sid})
                sc = _mutter("ScreenCast", scp, "ScreenCast.Session")
                s.stream_path = sc.RecordMonitor("", {"cursor-mode": dbus.UInt32(EMBEDDED)})
                sobj = bus.get_object(M + "ScreenCast", s.stream_path)

                def added(node):
                    params = dbus.Interface(sobj, dbus.PROPERTIES_IFACE).Get(
                        M + "ScreenCast.Stream", "Parameters")
                    log("stream node", int(node))
                    stream = (dbus.UInt32(int(node)), dbus.Dictionary({
                        "position": params.get("position", dbus.Struct((0, 0), signature="ii")),
                        "size": params.get("size", dbus.Struct((0, 0), signature="ii")),
                        "source_type": dbus.UInt32(1)}, signature="sv"))
                    ok(dbus.UInt32(0), dbus.Dictionary({
                        "streams": dbus.Array([stream], signature="(ua{sv})"),
                        "devices": dbus.UInt32(s.devices),
                        "clipboard_enabled": dbus.Boolean(False)}, signature="sv"))
                bus.add_signal_receiver(added, "PipeWireStreamAdded",
                                        M + "ScreenCast.Stream", path=s.stream_path)
            s.rd.Start()
            if not s.want_screen:
                ok(dbus.UInt32(0), dbus.Dictionary({"devices": dbus.UInt32(s.devices)},
                                                   signature="sv"))
        except dbus.DBusException as e:
            log("start failed:", e)
            ok(dbus.UInt32(2), dbus.Dictionary({}, signature="sv"))


def _m(iface, member, sig, out="ua{sv}", **kw):
    def deco(fn):
        fn.__name__ = member
        return dbus.service.method(iface, in_signature=sig, out_signature=out, **kw)(fn)
    return deco


def _create(self, handle, session_handle, app_id, options):
    log("CreateSession", session_handle, app_id)
    sessions[str(session_handle)] = Session(session_handle)
    return dbus.UInt32(0), dbus.Dictionary({"session_id": str(session_handle)}, signature="sv")


def sc_create(self, handle, session_handle, app_id, options):
    return _create(self, handle, session_handle, app_id, options)


def rd_create(self, handle, session_handle, app_id, options):
    return _create(self, handle, session_handle, app_id, options)


def sc_start(self, handle, session_handle, app_id, parent_window, options, ok, err):
    self._start(sessions[str(session_handle)], ok)


def rd_start(self, handle, session_handle, app_id, parent_window, options, ok, err):
    self._start(sessions[str(session_handle)], ok)


def sc_select(self, handle, session_handle, app_id, options):
    sessions[str(session_handle)].want_screen = True   # cursor_mode ignored: always embedded
    return dbus.UInt32(0), dbus.Dictionary({}, signature="sv")


def rd_select(self, handle, session_handle, app_id, options):
    sessions[str(session_handle)].devices = int(options.get("types", 3))
    return dbus.UInt32(0), dbus.Dictionary({}, signature="sv")


def rd_eis(self, session_handle, app_id, options):
    return sessions[str(session_handle)].rd.ConnectToEIS(dbus.Dictionary({}, signature="sv"))


def _forward(name, conv):
    """Notify* passthrough with the fixed arity dbus-python needs."""
    def fn2(self, sh, o, a1, a2):
        s = sessions[str(sh)]
        getattr(s.rd, name)(*conv(s, o, a1, a2))

    def fn3(self, sh, o, a1, a2, a3):
        s = sessions[str(sh)]
        getattr(s.rd, name)(*conv(s, o, a1, a2, a3))
    return fn3 if name == "NotifyPointerMotionAbsolute" else fn2


def _motion(s, o, dx, dy):
    return dx, dy


def _abs(s, o, stream, x, y):
    return s.stream_path, x, y


def _button(s, o, b, st):
    return b, bool(st)


def _axis(s, o, dx, dy):
    return dx, dy, dbus.UInt32(1 if o.get("finish") else 0)


def _discrete(s, o, axis, n):
    return axis, n


def _key(s, o, k, st):
    return dbus.UInt32(k), bool(st)


SC_METHODS = {
    "CreateSession": _m(SC_IFACE, "CreateSession", "oosa{sv}")(sc_create),
    "SelectSources": _m(SC_IFACE, "SelectSources", "oosa{sv}")(sc_select),
    "Start": _m(SC_IFACE, "Start", "oossa{sv}", async_callbacks=("ok", "err"))(sc_start),
}
RD_METHODS = {
    "CreateSession": _m(RD_IFACE, "CreateSession", "oosa{sv}")(rd_create),
    "SelectDevices": _m(RD_IFACE, "SelectDevices", "oosa{sv}")(rd_select),
    "Start": _m(RD_IFACE, "Start", "oossa{sv}", async_callbacks=("ok", "err"))(rd_start),
    "ConnectToEIS": _m(RD_IFACE, "ConnectToEIS", "osa{sv}", out="h")(rd_eis),
    "NotifyPointerMotion": _m(RD_IFACE, "NotifyPointerMotion", "oa{sv}dd", out="")(
        _forward("NotifyPointerMotionRelative", _motion)),
    "NotifyPointerMotionAbsolute": _m(RD_IFACE, "NotifyPointerMotionAbsolute", "oa{sv}udd",
                                      out="")(_forward("NotifyPointerMotionAbsolute", _abs)),
    "NotifyPointerButton": _m(RD_IFACE, "NotifyPointerButton", "oa{sv}iu", out="")(
        _forward("NotifyPointerButton", _button)),
    "NotifyPointerAxis": _m(RD_IFACE, "NotifyPointerAxis", "oa{sv}dd", out="")(
        _forward("NotifyPointerAxis", _axis)),
    "NotifyPointerAxisDiscrete": _m(RD_IFACE, "NotifyPointerAxisDiscrete", "oa{sv}ui", out="")(
        _forward("NotifyPointerAxisDiscrete", _discrete)),
    "NotifyKeyboardKeycode": _m(RD_IFACE, "NotifyKeyboardKeycode", "oa{sv}iu", out="")(
        _forward("NotifyKeyboardKeycode", _key)),
    "NotifyKeyboardKeysym": _m(RD_IFACE, "NotifyKeyboardKeysym", "oa{sv}iu", out="")(
        _forward("NotifyKeyboardKeysym", _key)),
}
# ScreenCast and RemoteDesktop share member names: one class level each (see docstring).
ScreenCastLevel = type("ScreenCastLevel", (Portal,), SC_METHODS)
Seat = type("Seat", (ScreenCastLevel,), RD_METHODS)


class Monitor:
    """Mutter virtual monitor held at w x h by a fakesink consumer.
    ponytail: always-copy costs one copy per painted frame (unmeasurable in the
    spike at 1440p60); drop it if a box's CPU budget ever says otherwise."""
    def __init__(self, w, h):
        self.w, self.h, self.pipe, self.playing = w, h, None, False
        path = _mutter("ScreenCast", "/org/gnome/Mutter/ScreenCast",
                       "ScreenCast").CreateSession(dbus.Dictionary({}, signature="sv"))
        self.sess = _mutter("ScreenCast", path, "ScreenCast.Session")
        stream = self.sess.RecordVirtual(dbus.Dictionary(
            {"cursor-mode": dbus.UInt32(EMBEDDED), "is-platform": dbus.Boolean(True)},
            signature="sv"))
        bus.add_signal_receiver(self._added, "PipeWireStreamAdded",
                                M + "ScreenCast.Stream", path=stream)
        self.sess.Start()

    def _added(self, node):
        self.pipe = Gst.parse_launch(
            f"pipewiresrc path={int(node)} always-copy=true ! "
            f"video/x-raw,width={self.w},height={self.h},max-framerate=60/1 ! "
            "fakesink sync=false")
        self.pipe.set_state(Gst.State.PLAYING)
        self.playing = True
        log("virtual monitor stream", int(node), f"{self.w}x{self.h}")

    def is_current(self) -> bool:
        dc = _mutter("DisplayConfig", "/org/gnome/Mutter/DisplayConfig", "DisplayConfig")
        _serial, monitors, _logical, _props = dc.GetCurrentState()
        return any(mode[6].get("is-current") and (int(mode[1]), int(mode[2])) == (self.w, self.h)
                   for _spec, modes, _mprops in monitors for mode in modes)

    def stop(self):
        if self.pipe is not None:
            self.pipe.set_state(Gst.State.NULL)
        try:
            self.sess.Stop()
        except dbus.DBusException:
            pass


def _write_ready(path: str, text: str) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        f.write(text)
    os.replace(tmp, path)


def selftest() -> int:
    sc, rd = ScreenCastLevel.__dict__, Seat.__dict__
    assert sc["CreateSession"]._dbus_interface == SC_IFACE
    assert sc["Start"]._dbus_interface == SC_IFACE
    assert rd["CreateSession"]._dbus_interface == RD_IFACE
    assert rd["Start"]._dbus_interface == RD_IFACE
    assert rd["NotifyPointerMotionAbsolute"]._dbus_in_signature == "oa{sv}udd"
    assert rd["ConnectToEIS"]._dbus_out_signature == "h"
    assert parse_size("2552x1294") == (2552, 1294)
    print("selftest ok", flush=True)
    return 0


def main(argv) -> int:
    global bus
    if argv[1:] == ["--selftest"]:
        return selftest()
    w, h = parse_size(argv[1])
    DBusGMainLoop(set_as_default=True)
    Gst.init(None)
    bus = dbus.SessionBus()
    name = dbus.service.BusName(BUS_NAME, bus)  # noqa: F841 — held for life
    Seat()
    ready = os.environ.get("STYX_PORTAL_READY", "")
    loop = GLib.MainLoop()
    st = {"rc": 0, "tries": 0, "frontend": None}
    mon = Monitor(w, h)

    def poll():
        if mon.playing and mon.is_current():
            exe = next((p for p in FRONTENDS if os.path.exists(p)), None)
            if exe is None:
                log("xdg-desktop-portal not found")
                st["rc"] = 1
                loop.quit()
                return False
            st["frontend"] = subprocess.Popen([exe, "--replace"])
            if ready:
                _write_ready(ready, f"{w}x{h}")
            log("ready", f"{w}x{h}")
            return False
        st["tries"] += 1
        if st["tries"] >= LIVE_TRIES:
            log(f"virtual monitor {w}x{h} never became current")
            st["rc"] = 1
            loop.quit()
            return False
        return True

    def on_term():
        loop.quit()
        return False

    GLib.timeout_add(200, poll)
    GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGTERM, on_term)
    loop.run()
    if st["frontend"] is not None:
        st["frontend"].terminate()
        try:
            st["frontend"].wait(timeout=5)
        except subprocess.TimeoutExpired:
            st["frontend"].kill()
    mon.stop()
    if ready:
        try:
            os.unlink(ready)
        except OSError:
            pass
    return st["rc"]


if __name__ == "__main__":
    sys.exit(main(sys.argv))
```

- [ ] **Step 4: Run the selftest with the system python, then the suite**

Run: `cd /home/user/code/remote-access/agent && /usr/bin/python3 seat_portal.py --selftest && wc -l seat_portal.py`
Expected: `selftest ok`, line count < 300.
Run: `cd /home/user/code/remote-access/agent && ../backend/.venv/bin/python -m pytest -q tests`
Expected: all pass; `test_seat_portal.py` reported as skipped.

- [ ] **Step 5: Commit**

```bash
cd /home/user/code/remote-access
git add agent/seat_portal.py agent/tests/test_seat_portal.py
git commit -m "feat(agent): consent-free seat portal backend and virtual monitor helper

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: `agent/seat_gnome.py` — monitorless GNOME, portal dir, helper lifecycle, refit

**Files:**
- Modify: `agent/seat_gnome.py`
- Test: `agent/tests/test_seat_gnome.py`

**Interfaces:**
- Consumes: `refit.write_size(path, w, h)` (Task 1); `seat_portal.py` CLI contract (Task 3): `/usr/bin/python3 <install>/seat_portal.py WxH`, env `STYX_PORTAL_READY`, ready file content `WxH`.
- Produces (used by Task 6):
  - `build_launch_script(sink: str, bus_file: str, portal_dir: str) -> str` (width/height params REMOVED)
  - `write_portal_dir(d: Path, src: Path = PORTAL_SRC) -> None`
  - `GnomeSeat.size_file: Path` (= `<install>/seat-size`), `GnomeSeat.size: tuple[int, int] | None`
  - `GnomeSeat.start(width, height)` (unchanged signature), `GnomeSeat.ready(timeout=20) -> bool` (now also starts the helper), `GnomeSeat.refit(w: int, h: int) -> bool`, `GnomeSeat.alive()` (GNOME and helper), `GnomeSeat.stop()` (also stops helper)
  - `gnome_available()` additionally fails with `"seat helper deps missing (python3-dbus, python3-gi, gstreamer1.0-pipewire)"`
  - REMOVED: `CONSENT_PENDING_S`, `TOKEN_PATH`, `CONSENT_ERROR`, `needs_consent`. `Escalation` and `pick_seat_shell` stay.

- [ ] **Step 1: Update/add tests** in `agent/tests/test_seat_gnome.py`.

Change `test_launch_script_scrubs_display_and_sets_activation_env_before_exec`: call `seat_gnome.build_launch_script("styx-seat", "/tmp/bus", "/p")` instead of `build_launch_script(2560, 1440, "styx-seat", "/tmp/bus")`, delete the line `assert "--virtual-monitor 2560x1440" in lines[exe]`, and add:

```python
    assert "--virtual-monitor" not in s
    assert "export XDG_DESKTOP_PORTAL_DIR=/p" in s
    act = next(i for i, l in enumerate(lines) if l.startswith("dbus-update-activation-environment"))
    assert "XDG_DESKTOP_PORTAL_DIR=/p" in lines[act] and act < exe
```

In `test_ready_needs_socket_and_bus`, before the `ready()` call that is expected to return True, add `monkeypatch.setattr(seat, "_start_helper", lambda w, h: True)` and set `seat.size = (2560, 1440)` (read the test first; keep its existing assertions).

Append:

```python
def test_write_portal_dir_routes_screencast_and_remote_desktop_to_styx(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "gnome.portal").write_text("[portal]\n")
    d = tmp_path / "portals"
    seat_gnome.write_portal_dir(d, src)
    seat_gnome.write_portal_dir(d, src)                       # idempotent
    assert (d / "gnome.portal").exists()
    assert "DBusName=org.freedesktop.impl.portal.desktop.styx" in (d / "styx.portal").read_text()
    for n in ("portals.conf", "ubuntu-portals.conf", "gnome-portals.conf"):
        t = (d / n).read_text()
        assert "org.freedesktop.impl.portal.ScreenCast=styx;" in t
        assert "org.freedesktop.impl.portal.RemoteDesktop=styx;" in t


def _fake_proc(rc=None):
    return type("P", (), {"poll": lambda self: rc, "pid": 0})()


def test_refit_success_persists_size(tmp_path, monkeypatch):
    seat = seat_gnome.GnomeSeat(tmp_path, str(tmp_path), log=subprocess.DEVNULL)
    seat.bus = "unix:path=/b"

    def spawn(w, h):
        seat.ready_file.write_text(f"{w}x{h}")
        return _fake_proc()
    monkeypatch.setattr(seat, "_spawn_helper", spawn)
    monkeypatch.setattr(seat, "_stop_helper", lambda: None)
    assert seat.refit(2552, 1294) is True
    assert seat.size == (2552, 1294)
    assert (tmp_path / "seat-size").read_text() == "2552x1294"


def test_refit_failure_restores_previous_size(tmp_path, monkeypatch):
    seat = seat_gnome.GnomeSeat(tmp_path, str(tmp_path), log=subprocess.DEVNULL)
    seat.bus = "unix:path=/b"
    seat.size = (1920, 1080)
    calls = []

    def spawn(w, h):
        calls.append((w, h))
        if (w, h) == (1920, 1080):
            seat.ready_file.write_text("1920x1080")
            return _fake_proc()
        return _fake_proc(rc=1)                                # helper died
    monkeypatch.setattr(seat, "_spawn_helper", spawn)
    monkeypatch.setattr(seat, "_stop_helper", lambda: None)
    assert seat.refit(2552, 1294) is False
    assert calls == [(2552, 1294), (1920, 1080)]
    assert seat.size == (1920, 1080)


def test_alive_requires_helper_once_started(tmp_path):
    seat = seat_gnome.GnomeSeat(tmp_path, str(tmp_path), log=subprocess.DEVNULL)
    seat._proc = _fake_proc()
    assert seat.alive() is True                               # helper not started yet
    seat._helper = _fake_proc(rc=1)
    assert seat.alive() is False


def test_gnome_available_reports_missing_helper_deps(monkeypatch):
    monkeypatch.setattr(seat_gnome.shutil, "which", lambda n: "/usr/bin/gnome-shell")

    def run(cmd, *a, **k):
        if cmd[0] == "gnome-shell":
            return subprocess.CompletedProcess(cmd, 0, "GNOME Shell 46.0\n", "")
        return subprocess.CompletedProcess(cmd, 1, "", "ModuleNotFoundError")
    monkeypatch.setattr(seat_gnome.subprocess, "run", run)
    ok, why = seat_gnome.gnome_available()
    assert ok is False and "python3-dbus" in why
```

Delete any test in this file that references `needs_consent`, `TOKEN_PATH` or `CONSENT_*` (none expected; grep to confirm).

- [ ] **Step 2: Run to verify failures**

Run: `cd /home/user/code/remote-access/agent && ../backend/.venv/bin/python -m pytest -q tests/test_seat_gnome.py`
Expected: FAIL (`build_launch_script` arity, missing `write_portal_dir`, `refit`, `_spawn_helper`, `ready_file`).

- [ ] **Step 3: Implement** in `agent/seat_gnome.py`.

3a. Imports: add `import refit` after the stdlib imports (keep `from pathlib import Path`).

3b. Update the module docstring's second paragraph to: `The activation env MUST be set before anything can activate a portal; the seat routes ScreenCast/RemoteDesktop to our own consent-free backend (seat_portal.py), selected through XDG_DESKTOP_PORTAL_DIR.`

3c. Replace `build_launch_script` with:

```python
def build_launch_script(sink: str, bus_file: str, portal_dir: str) -> str:
    sink, bus_file, portal_dir = (shlex.quote(v) for v in (sink, bus_file, portal_dir))
    return "\n".join([
        "#!/bin/bash",
        "# generated by styx-agent: headless GNOME seat (do not edit)",
        "unset DISPLAY WAYLAND_DISPLAY XAUTHORITY",
        "export XDG_SESSION_TYPE=wayland XDG_CURRENT_DESKTOP=ubuntu:GNOME "
        "XDG_SESSION_DESKTOP=ubuntu GNOME_SHELL_SESSION_MODE=ubuntu",
        f"export PULSE_SINK={sink}",
        f"export XDG_DESKTOP_PORTAL_DIR={portal_dir}",
        f"dbus-update-activation-environment DISPLAY= WAYLAND_DISPLAY={SOCKET} "
        f"XDG_SESSION_TYPE=wayland XDG_CURRENT_DESKTOP=ubuntu:GNOME PULSE_SINK={sink} "
        f"XDG_DESKTOP_PORTAL_DIR={portal_dir}",
        f'echo "$DBUS_SESSION_BUS_ADDRESS" > {bus_file}',
        # No --virtual-monitor: seat_portal.py owns the monitor and its size.
        f"exec gnome-shell --headless --wayland --no-x11 --wayland-display={SOCKET}",
        "",
    ])
```

3d. Add after `MIN_GNOME = 46`:

```python
SYS_PYTHON = "/usr/bin/python3"
HELPER_READY_S = 10
PORTAL_SRC = Path("/usr/share/xdg-desktop-portal/portals")
STYX_PORTAL = ("[portal]\nDBusName=org.freedesktop.impl.portal.desktop.styx\n"
               "Interfaces=org.freedesktop.impl.portal.ScreenCast;"
               "org.freedesktop.impl.portal.RemoteDesktop;\nUseIn=gnome\n")
PORTALS_CONF = ("[preferred]\ndefault=gnome;gtk;\n"
                "org.freedesktop.impl.portal.Secret=gnome-keyring;\n"
                "org.freedesktop.impl.portal.ScreenCast=styx;\n"
                "org.freedesktop.impl.portal.RemoteDesktop=styx;\n")
_HELPER_DEPS = ("import dbus, gi; gi.require_version('Gst', '1.0'); "
                "from gi.repository import Gst; Gst.init(None); "
                "assert Gst.ElementFactory.find('pipewiresrc')")


def write_portal_dir(d: Path, src: Path = PORTAL_SRC) -> None:
    """Portal dir for the seat's frontend: the distro's backends plus ours,
    with ScreenCast/RemoteDesktop routed to styx (the frontend reads
    portals.conf from XDG_DESKTOP_PORTAL_DIR)."""
    d.mkdir(parents=True, exist_ok=True)
    for p in src.glob("*.portal"):
        if p.name != "styx.portal":
            shutil.copy(p, d / p.name)
    (d / "styx.portal").write_text(STYX_PORTAL)
    for name in ("portals.conf", "ubuntu-portals.conf", "gnome-portals.conf"):
        (d / name).write_text(PORTALS_CONF)
```

3e. In `gnome_available()`, before the final `return True, ""`, add:

```python
    try:
        rc = subprocess.run([SYS_PYTHON, "-c", _HELPER_DEPS], capture_output=True,
                            timeout=20).returncode
    except (OSError, subprocess.TimeoutExpired):
        rc = 1
    if rc:
        return False, "seat helper deps missing (python3-dbus, python3-gi, gstreamer1.0-pipewire)"
```

3f. Delete the consent block: the comment `# GNOME seat consent (spec §5.4/§5.5)…`, `CONSENT_PENDING_S`, `TOKEN_PATH`, `CONSENT_ERROR`, and the function `needs_consent`.

3g. In `GnomeSeat.__init__` add:

```python
        self.portal_dir = self.install_dir / "portals"
        self.size_file = self.install_dir / "seat-size"
        self.ready_file = Path(runtime_dir) / "styx-seat-portal.ready"
        self.size: tuple[int, int] | None = None
        self._helper = None
```

3h. In `GnomeSeat.start`, set `self.size = (width, height)` right after `self._started = True`, call `write_portal_dir(self.portal_dir)` before writing the script, and change the script line to:

```python
        self.script.write_text(build_launch_script(SEAT_SINK, str(self.bus_file),
                                                   str(self.portal_dir)))
```

3i. In `GnomeSeat.ready`, replace `return True` (the line after the `_shell_answers()` condition) with `return self._start_helper(*self.size)`.

3j. Replace `alive` with:

```python
    def alive(self) -> bool:
        """GNOME up and, once started, the seat helper too (it owns the monitor
        and the portal backend; without it capture and input are dead)."""
        return (self._proc is not None and self._proc.poll() is None
                and (self._helper is None or self._helper.poll() is None))
```

3k. Add these methods to `GnomeSeat` (after `alive`):

```python
    def _spawn_helper(self, w: int, h: int):
        env = {k: v for k, v in os.environ.items() if k not in _SCRUB}
        env.update({"XDG_RUNTIME_DIR": self.runtime_dir,
                    "DBUS_SESSION_BUS_ADDRESS": self.bus or "",
                    "XDG_DESKTOP_PORTAL_DIR": str(self.portal_dir),
                    "XDG_CURRENT_DESKTOP": "ubuntu:GNOME", "XDG_SESSION_TYPE": "wayland",
                    "STYX_PORTAL_READY": str(self.ready_file)})
        return subprocess.Popen([SYS_PYTHON, str(self.install_dir / "seat_portal.py"),
                                 f"{w}x{h}"], env=env, stdout=self.log, stderr=self.log,
                                start_new_session=True)

    def _start_helper(self, w: int, h: int) -> bool:
        """(Re)start the helper at w x h; True once it reports that size live."""
        self._stop_helper()
        self.ready_file.unlink(missing_ok=True)
        self._helper = self._spawn_helper(w, h)
        deadline = time.monotonic() + HELPER_READY_S
        while time.monotonic() < deadline:
            if self._helper.poll() is not None:
                return False
            try:
                if self.ready_file.read_text().strip() == f"{w}x{h}":
                    self.size = (w, h)
                    refit.write_size(self.size_file, w, h)
                    return True
            except OSError:
                pass
            time.sleep(0.1)
        self._stop_helper()
        return False

    def refit(self, w: int, h: int) -> bool:
        """New monitor size = new helper. On failure fall back to the old size so
        the seat is never left monitorless. Caller stops selkies first."""
        old = self.size
        if self._start_helper(w, h):
            return True
        if old:
            self._start_helper(*old)
        return False

    def _stop_helper(self) -> None:
        p, self._helper = self._helper, None
        if p is None or p.poll() is not None:
            return
        try:
            os.killpg(p.pid, signal.SIGTERM)
            try:
                p.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(p.pid, signal.SIGKILL)
                p.wait()
        except ProcessLookupError:
            pass
```

3l. In `GnomeSeat.stop`, add `self._stop_helper()` as the first line of the method body.

- [ ] **Step 4: Run tests and size check**

Run: `cd /home/user/code/remote-access/agent && ../backend/.venv/bin/python -m pytest -q tests/test_seat_gnome.py && wc -l seat_gnome.py`
Expected: all pass; `seat_gnome.py` < 500 lines.
Note: `tests/test_styx_agent.py` will fail now (it imports `needs_consent`/`CONSENT_ERROR`); Task 6 fixes that. Do not touch `styx_agent.py` in this task.

- [ ] **Step 5: Commit**

```bash
cd /home/user/code/remote-access
git add agent/seat_gnome.py agent/tests/test_seat_gnome.py
git commit -m "feat(agent): GNOME seat runs seat_portal helper, refits monitor, drops consent path

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: `agent/gateway.py` — refit on first resize, 503 while pending, reload shim

**Files:**
- Modify: `agent/gateway.py` (`create_app` params ~line 180; `ws_proxy`/`pump` ~257–318; `index` ~327–342; `main` ~440–455)
- Test: `agent/tests/test_gateway.py`

**Interfaces:**
- Consumes: `refit.parse_resize`, `refit.decide`, `refit.read_size`, `refit.request`, `refit.pending`, `refit.inject_reload`, `refit.CLOSE_CODE` (Task 1).
- Produces (used by Task 6): `create_app(..., seat_dir: str = "")` replaces the `cursor_workaround` param; env `STYX_GW_SEAT_DIR` replaces `STYX_GW_CURSOR_WORKAROUND`. Files used: `<seat_dir>/seat-size` (read), `<seat_dir>/refit-request` (written).

- [ ] **Step 1: Write failing tests** — append to `agent/tests/test_gateway.py`:

```python
async def _recording_upstream(received):
    from aiohttp import web

    async def upstream_ws(request):
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        async for m in ws:
            received.append(m.data)
        return ws
    app = web.Application()
    app.router.add_get("/api/websockets", upstream_ws)
    return app


async def _refit_pair(tmp_path, received, seat_dir):
    from aiohttp.test_utils import TestClient, TestServer
    up = TestClient(TestServer(await _recording_upstream(received)))
    await up.start_server()
    client = TestClient(TestServer(gateway.create_app(
        "styx", "pw", upstream_port=up.server.port, seat_dir=seat_dir)))
    await client.start_server()
    return up, client


@pytest.mark.asyncio
async def test_first_resize_mismatch_requests_refit_and_closes_4002(tmp_path):
    import asyncio
    (tmp_path / "seat-size").write_text("1920x1080")
    received = []
    up, client = await _refit_pair(tmp_path, received, str(tmp_path))
    try:
        ws = await client.ws_connect("/websocket", headers={"Authorization": _basic("styx", "pw")})
        await ws.send_str("SETTINGS,{}")
        await ws.send_str("r,2552x1294,primary")
        msg = await asyncio.wait_for(ws.receive(), timeout=3)
        assert msg.type == aiohttp.WSMsgType.CLOSE and msg.data == 4002
        await asyncio.sleep(0.1)
    finally:
        await client.close()
        await up.close()
    assert (tmp_path / "refit-request").read_text() == "2552x1294"
    assert "SETTINGS,{}" in received
    assert not any(isinstance(m, str) and m.startswith("r,") for m in received)


@pytest.mark.asyncio
async def test_matching_resize_is_forwarded(tmp_path):
    import asyncio
    (tmp_path / "seat-size").write_text("2552x1294")
    received = []
    up, client = await _refit_pair(tmp_path, received, str(tmp_path))
    try:
        ws = await client.ws_connect("/websocket", headers={"Authorization": _basic("styx", "pw")})
        await ws.send_str("r,2560x1300,primary")
        await asyncio.sleep(0.2)
        await ws.close()
    finally:
        await client.close()
        await up.close()
    assert "r,2560x1300,primary" in received
    assert not (tmp_path / "refit-request").exists()


@pytest.mark.asyncio
async def test_second_resize_in_window_is_forwarded(tmp_path):
    """Only a connection's FIRST r, can refit; later ones letterbox upstream."""
    import asyncio
    (tmp_path / "seat-size").write_text("2552x1294")
    received = []
    up, client = await _refit_pair(tmp_path, received, str(tmp_path))
    try:
        ws = await client.ws_connect("/websocket", headers={"Authorization": _basic("styx", "pw")})
        await ws.send_str("r,2552x1294,primary")
        await ws.send_str("r,1280x720,primary")
        await asyncio.sleep(0.2)
        await ws.close()
    finally:
        await client.close()
        await up.close()
    assert "r,1280x720,primary" in received
    assert not (tmp_path / "refit-request").exists()


@pytest.mark.asyncio
async def test_resize_untouched_without_seat_dir(tmp_path):
    import asyncio
    received = []
    up, client = await _refit_pair(tmp_path, received, "")
    try:
        ws = await client.ws_connect("/websocket", headers={"Authorization": _basic("styx", "pw")})
        await ws.send_str("r,2552x1294,primary")
        await asyncio.sleep(0.2)
        await ws.close()
    finally:
        await client.close()
        await up.close()
    assert "r,2552x1294,primary" in received
```

Also add an index test. Read the existing `_upstream_app()` helper (around line 360) first; it serves `/` with HTML. Append:

```python
@pytest.mark.asyncio
async def test_index_503_while_refit_pending_and_injects_seat_shims(tmp_path):
    from aiohttp.test_utils import TestClient, TestServer
    up = TestClient(TestServer(await _upstream_app()))
    await up.start_server()
    client = TestClient(TestServer(gateway.create_app(
        "styx", "pw", upstream_port=up.server.port, seat_dir=str(tmp_path))))
    await client.start_server()
    h = {"Authorization": _basic("styx", "pw")}
    try:
        (tmp_path / "refit-request").write_text("2552x1294")
        r = await client.get("/", headers=h)
        assert r.status == 503
        (tmp_path / "refit-request").unlink()
        r = await client.get("/", headers=h)
        body = await r.text()
        assert r.status == 200 and 'id="styx-refit"' in body and 'id="styx-cursor"' in body
    finally:
        await client.close()
        await up.close()
```

If `_upstream_app()`'s HTML has no `</head>`, add `</head>` to the HTML it returns (this is test scaffolding only).

Find every existing test that passes `cursor_workaround=` to `create_app` (`grep -n cursor_workaround tests/test_gateway.py`) and change it to `seat_dir=str(tmp_path)` (enabled) or remove the argument (disabled), keeping the assertions about `styx-cursor`.

- [ ] **Step 2: Run to verify failures**

Run: `cd /home/user/code/remote-access/agent && ../backend/.venv/bin/python -m pytest -q tests/test_gateway.py`
Expected: FAIL — `create_app() got an unexpected keyword argument 'seat_dir'`.

- [ ] **Step 3: Implement** in `agent/gateway.py`.

3a. Add `import refit` after the other top-level imports (alongside the stdlib imports; it is a local module next to gateway.py).

3b. `create_app` signature: replace `cursor_workaround: bool = False` with `seat_dir: str = ""`. Right after `stream = {...}` add:

```python
    # GNOME seat size-at-connect (refit.py): only a connection's first r, can refit.
    size_file = os.path.join(seat_dir, "seat-size") if seat_dir else ""
    refit_file = os.path.join(seat_dir, "refit-request") if seat_dir else ""
    last_refit = {"ts": float("-inf")}
```

3c. In `ws_proxy`, change the `pump` signature to `async def pump(src, dst, on_activity=None, on_binary=None, intercept=None):` and in its TEXT branch, after `on_activity(msg.data)` handling and before `await dst.send_str(msg.data)`, add:

```python
                            if intercept and intercept(msg.data):
                                continue
```

Then, just before the `await asyncio.gather(...)` call, add:

```python
                first_resize = {"done": not seat_dir}

                def refit_on_first_resize(data) -> bool:
                    """True = swallow: seat is being rebuilt at the browser size."""
                    if first_resize["done"]:
                        return False
                    req = refit.parse_resize(data)
                    if req is None:
                        return False
                    first_resize["done"] = True
                    now = time.time()
                    target = refit.decide(req, refit.read_size(size_file), last_refit["ts"], now)
                    if target is None:
                        return False
                    last_refit["ts"] = now
                    refit.request(refit_file, *target)
                    asyncio.ensure_future(ws_server.close(code=refit.CLOSE_CODE, message=b"refit"))
                    return True
```

and change the first `pump(...)` call inside `gather` to:

```python
                await asyncio.gather(pump(ws_server, ws_client, on_activity=mark_input,
                                          intercept=refit_on_first_resize),
```

(keep the other two gather arguments as they are).

3d. In `index`, add as the first statement of the function body:

```python
        if refit_file and refit.pending(refit_file):
            return web.Response(status=503, text="resizing desktop")
```

and replace `html = inject_cursor_hide(html, cursor_workaround)` with:

```python
        html = inject_cursor_hide(html, bool(seat_dir))
        html = refit.inject_reload(html, bool(seat_dir))
```

3e. In `main()`, replace `cursor = os.environ.get("STYX_GW_CURSOR_WORKAROUND", "") == "1"` with `seat_dir = os.environ.get("STYX_GW_SEAT_DIR", "")` and `cursor_workaround=cursor` with `seat_dir=seat_dir`.

- [ ] **Step 4: Run tests and size check**

Run: `cd /home/user/code/remote-access/agent && ../backend/.venv/bin/python -m pytest -q tests/test_gateway.py tests/test_gateway_idle.py && wc -l gateway.py`
Expected: all pass; `gateway.py` ≤ 500 lines. If it is over, shorten only the comments you added in this task; do not move existing code.

- [ ] **Step 5: Commit**

```bash
cd /home/user/code/remote-access
git add agent/gateway.py agent/tests/test_gateway.py
git commit -m "feat(agent): gateway refits GNOME seat to browser size on first resize

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: `agent/styx_agent.py` + `agent/health.py` — wire refit, remove consent/grant, 0.6.0

**Files:**
- Modify: `agent/styx_agent.py`, `agent/health.py`
- Delete: `agent/grant.py`, `agent/tests/test_grant.py`
- Test: `agent/tests/test_styx_agent.py`, `agent/tests/test_health.py` (if it tests `seat_advisories`)

**Interfaces:**
- Consumes: `refit.read_size`, `refit.clamp`, `refit.wait_for_request`, `refit.clear_request` (Task 1); `GnomeSeat.size_file`, `GnomeSeat.install_dir`, `GnomeSeat.refit`, `GnomeSeat.alive` (Task 4); gateway env `STYX_GW_SEAT_DIR` (Task 5).
- Produces: `build_gateway_cmd(cfg, upstream_port, seat_dir: str = "")`; `health.seat_advisories(gnome: tuple[bool, str]) -> list` (token param removed); `AGENT_VERSION = "0.6.0"`; health payload without `needs_consent`.

- [ ] **Step 1: Update tests** in `agent/tests/test_styx_agent.py`:
  - Delete `test_needs_consent` and `test_consent_error_names_the_fix`.
  - Rename/replace `test_gateway_cmd_has_no_web_dir_and_passes_cursor_flag` with:

```python
def test_gateway_cmd_passes_seat_dir_only_for_gnome(tmp_path):
    cfg = {"install_dir": str(tmp_path), "selkies_user": "u", "selkies_password": "p",
           "port": 8443, "stream_settings": {"cursor_workaround": True}}
    _, env = styx_agent.build_gateway_cmd(cfg, 9000, seat_dir=str(tmp_path))
    assert env["STYX_GW_SEAT_DIR"] == str(tmp_path)
    assert "STYX_GW_CURSOR_WORKAROUND" not in env
    _, env = styx_agent.build_gateway_cmd(cfg, 9000)
    assert env["STYX_GW_SEAT_DIR"] == ""
```

  (Read the old test first and keep any `web` dir assertion it had.)
  - In `test_agent_version_bumped`, make it assert `styx_agent.AGENT_VERSION == "0.6.0"` (keep its existing style).
  - In the doctor tests around lines 255–284: remove the `TOKEN_PATH` monkeypatch and change `assert "doctor --grant" in out` to `assert "doctor --grant" not in out` (keep the other assertions).
  - In `test_health_payload_reports_mode_and_engine`, add `assert "needs_consent" not in payload` (use the test's variable name).

- [ ] **Step 2: Run to verify failures**

Run: `cd /home/user/code/remote-access/agent && ../backend/.venv/bin/python -m pytest -q tests/test_styx_agent.py`
Expected: FAIL (import errors for removed names / new assertions).

- [ ] **Step 3: Implement.**

3a. `agent/health.py` — replace `seat_advisories` with:

```python
def seat_advisories(gnome: tuple[bool, str]) -> list[tuple[str, bool, str]]:
    """GNOME seat advisories for doctor (never gating: labwc is the fallback)."""
    ok, why = gnome
    return [("GNOME seat available", ok, "" if ok else f"{why} — falling back to labwc")]
```

3b. `agent/styx_agent.py`:
  - `AGENT_VERSION = "0.6.0"`.
  - Imports: add `import refit`; from `seat_gnome` import only `Escalation, pick_seat_shell` (drop `CONSENT_ERROR`, `needs_consent`).
  - `build_gateway_cmd(cfg, upstream_port, seat_dir: str = "")`: replace the env line `"STYX_GW_CURSOR_WORKAROUND": ...` with `"STYX_GW_SEAT_DIR": seat_dir,`.
  - `health_payload`: delete the `"needs_consent": ...` entry and the now-unused `starving = ...` line if nothing else in the function uses it.
  - In `run()`, right after `gseat = (...)` is created, add:

```python
    refit_req = INSTALL_DIR / "refit-request"
    refit.clear_request(refit_req)        # stale request from a previous run
```

  - In `ensure_gnome_seat()`, replace the `gseat.start(int(ss.get("seat_width") or 2560), int(ss.get("seat_height") or 1440))` call with:

```python
        size = refit.read_size(gseat.size_file) or (
            int(ss.get("seat_width") or 2560), int(ss.get("seat_height") or 1440))
        gseat.start(*refit.clamp(*size))
```

  - Gateway spawn: change `cmd, env = build_gateway_cmd(cfg, internal_port)` to `cmd, env = build_gateway_cmd(cfg, internal_port, str(INSTALL_DIR) if gseat else "")`.
  - Watchdog block: delete `consent_pending = ...`, the `if gseat and needs_consent(starving): ... elif last_error == CONSENT_ERROR: ...` lines, and `not consent_pending` from the restart condition. Update the comment above it to drop the consent sentence.
  - Replace the final `time.sleep(interval)` of the loop with:

```python
        # GNOME seat: wake early when the gateway asks for a refit (size-at-connect).
        req = refit.wait_for_request(refit_req, interval) if gseat else time.sleep(interval)
        if req:
            if gseat.alive():
                print(f"refit: rebuilding seat monitor at {req[0]}x{req[1]}", flush=True)
                _terminate(procs["selkies"])
                procs["selkies"] = None
                if not gseat.refit(*req):
                    last_error = f"refit to {req[0]}x{req[1]} failed — kept previous size"
                last_engine_restart = time.monotonic()
            refit.clear_request(refit_req)
```

  - `doctor`: change `seat_advisories(seat_gnome.gnome_available(), seat_gnome.TOKEN_PATH.exists())` to `seat_advisories(seat_gnome.gnome_available())`.
  - `main`: delete the `if "--grant" in sys.argv:` branch (3 lines) and any usage text mentioning `--grant`.

3c. Delete `agent/grant.py` and `agent/tests/test_grant.py` (`git rm`).

3d. `grep -rn "grant\|needs_consent\|CONSENT\|TOKEN_PATH\|cursor_workaround" agent/*.py agent/tests/*.py` — only `test_gateway_cmd_passes_seat_dir_only_for_gnome`'s input dict may still mention `cursor_workaround`.

- [ ] **Step 4: Run all agent tests and size check**

Run: `cd /home/user/code/remote-access/agent && ../backend/.venv/bin/python -m pytest -q tests && wc -l styx_agent.py gateway.py seat_gnome.py`
Expected: all pass (test_packaging may fail until Task 7 — if it fails ONLY because `grant` is in its `ENTRY` list or `refit.py` is not served, continue; Task 7 fixes it). `styx_agent.py` ≤ 500.

- [ ] **Step 5: Commit**

```bash
cd /home/user/code/remote-access
git add -A agent/
git commit -m "feat(agent)!: agent 0.6.0 refits GNOME seat on connect; remove doctor --grant

BREAKING CHANGE: 'styx_agent.py doctor --grant' is gone; the GNOME seat no longer needs consent.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7: Backend + packaging — serve new modules, drop grant and cursor_workaround

**Files:**
- Modify: `backend/app/services/workstations.py` (`AGENT_UPDATE_FILES` ~line 136), `backend/app/routers/enroll.py` (`/grant.py` endpoint ~line 80), `agent/enroll.sh` (file loop ~line 262), `agent/tests/test_packaging.py` (`ENTRY`), `backend/app/config.py:75`, `backend/app/services/settings_store.py:89-92`, `backend/app/services/ws_settings.py:38-39`, `backend/app/routers/agent.py:77`
- Test: `backend/tests/test_ws_settings.py`, `backend/tests/test_workstation_agent_api.py`, `agent/tests/test_packaging.py`, plus a new backend test

**Interfaces:**
- Consumes: agent files `refit.py`, `seat_portal.py` (Tasks 1, 3); `grant.py` deleted (Task 6).
- Produces: enroll endpoints `/api/enroll/refit.py` and `/api/enroll/seat_portal.py`; `/api/enroll/grant.py` removed; effective stream settings no longer contain `cursor_workaround`.

- [ ] **Step 1: Update tests.**
  - `agent/tests/test_packaging.py`: set `ENTRY = ["styx_agent", "engine", "gateway", "seat_gnome", "seat_labwc", "health", "portal_api", "refit"]` and add at the end of `test_all_imported_local_modules_are_served` body: `assert "seat_portal.py" in served   # launched by path, not imported`.
  - `backend/tests/test_ws_settings.py`: remove `"WORKSTATION_CURSOR_WORKAROUND": True` from the settings dict (line 5), delete the `assert eff["cursor_workaround"] is True` line, and drop `"cursor_workaround"` from the tuple on line 39; add `assert "cursor_workaround" not in eff` to the test that previously asserted it.
  - `backend/tests/test_workstation_agent_api.py:153`: change to `assert ss["seat_shell"] == "gnome" and "cursor_workaround" not in ss`.
  - Add to `backend/tests/test_ws_settings.py`:

```python
def test_removed_cursor_setting_row_is_ignored():
    """Old DBs still hold WORKSTATION_CURSOR_WORKAROUND; it must not leak or crash."""
    sys_settings = {**SYS, "WORKSTATION_CURSOR_WORKAROUND": True}
    eff = resolve_stream_settings({}, sys_settings, "0.6.0")
    assert "cursor_workaround" not in eff
```

  (`SYS` and `resolve_stream_settings(stream_settings, sys_settings, agent_version)` are the file's existing names.)

- [ ] **Step 2: Run to verify failures**

Run: `cd /home/user/code/remote-access/backend && .venv/bin/python -m pytest -q tests/test_ws_settings.py tests/test_workstation_agent_api.py` and `cd /home/user/code/remote-access/agent && ../backend/.venv/bin/python -m pytest -q tests/test_packaging.py`
Expected: FAIL.

- [ ] **Step 3: Implement.**
  - `backend/app/services/workstations.py` `AGENT_UPDATE_FILES`: replace `("grant.py", "grant.py"),` with `("refit.py", "refit.py"),` and `("seat_portal.py", "seat_portal.py"),`.
  - `backend/app/routers/enroll.py`: replace the `/grant.py` endpoint with:

```python
@router.get("/refit.py")
async def refit_py():
    return _serve("refit.py")


@router.get("/seat_portal.py")
async def seat_portal_py():
    return _serve("seat_portal.py")
```

  - `agent/enroll.sh` file loop: replace `"grant.py grant.py"` with `"refit.py refit.py" "seat_portal.py seat_portal.py"`.
  - Remove `WORKSTATION_CURSOR_WORKAROUND` from `backend/app/config.py`, its `_spec(...)` entry in `settings_store.py`, the `eff["cursor_workaround"] = ...` lines in `ws_settings.py`, and the dict entry in `routers/agent.py:77`.
  - Check how `settings_store` loads persisted rows: if it iterates DB rows and looks each key up in the spec table, make sure an unknown key is skipped (not a KeyError). If it already skips, change nothing.
  - `grep -rn "grant\|cursor_workaround\|CURSOR_WORKAROUND" backend/app frontend/src agent/enroll.sh docs/*.md 2>/dev/null | grep -v node_modules` — remove remaining user-facing references (docs mentioning `doctor --grant` get one line: GNOME seat needs no consent since agent 0.6.0).

- [ ] **Step 4: Run everything**

Run: `cd /home/user/code/remote-access/backend && .venv/bin/python -m pytest -q && .venv/bin/python -m ruff check app/ tests/`
Run: `cd /home/user/code/remote-access/agent && ../backend/.venv/bin/python -m pytest -q tests`
Expected: all pass, ruff clean.

- [ ] **Step 5: Commit**

```bash
cd /home/user/code/remote-access
git add -A backend agent docs
git commit -m "feat: serve seat_portal/refit agent modules; drop grant.py and cursor_workaround setting

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 8 (controller, live): deploy to EliteMini and verify

Not a subagent task — the controller runs it after the final whole-branch review and with the user's go-ahead (merge + upgrade are outward-facing).

- [ ] **Step 1:** Merge to `main`; rebuild/restart the backend container (`docker compose up -d --build backend`), confirm `curl -sf https://s.jmolabs.dev/api/enroll/seat_portal.py | head -3` returns the module.
- [ ] **Step 2:** On EliteMini run the update one-liner from the portal (enroll.sh `--upgrade`); `systemctl --user status styx-agent` active; `styx_agent.py doctor` shows "GNOME seat available ✓" and no grant row.
- [ ] **Step 3:** `tail -n 30 ~/.local/share/styx-agent/logs/seat.log` (use the real install dir) shows `[seat-portal] ready WxH`; no consent dialog appears anywhere (physical desktop included).
- [ ] **Step 4:** User checks through Cloudflare: one steady cursor; sharp text; reload with a different window size → desktop refits to 1:1 within ~3 s with open windows preserved; resize mid-session letterboxes without freezing; no "Waiting for stream".
- [ ] **Step 5:** Log results to open-brain (milestone update) and the memory file; GAME-01 upgrade when it comes online.
