# Selkies 2.0 Phase 0 (Engine + GNOME Seat) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run enrolled workstations on selkies 2.0 / pixelflux 2.1 with a real headless GNOME seat (labwc kept as fallback), shipped as agent 0.5.0.

**Architecture:** A new `seat_gnome.py` owns a headless `gnome-shell` on a private D-Bus; selkies 2.0 captures it through `--wayland-host-display` (xdg-desktop-portal). The gateway becomes a single-upstream reverse proxy that still injects our shims. The backend gains one settings resolver that merges system defaults with per-workstation overrides and gates 2.0-only keys by agent version.

**Tech Stack:** Python 3.12, aiohttp (gateway), FastAPI + SQLModel (backend), pytest/pytest-asyncio, bash (enroll/build scripts), selkies 2.0.0 + pixelflux 2.1.0 + pcmflux 2.1.0 wheels, GNOME Shell ≥ 46.

**Spec:** `docs/superpowers/specs/2026-10-03-selkies2-gnome-seat-design.md`

## Global Constraints

- Pins: `selkies==2.0.0`, `pixelflux==2.1.0`, `pcmflux==2.1.0`; no git-commit selkies.
- No toolchains, PPAs or compiling on enrolled boxes; all wheels prebuilt on the server.
- Selkies binds loopback only; `--enable-basic-auth=false` (gateway owns auth). No new ports.
- Never run `gnome-shell --unsafe-mode`.
- Seat session env: `DISPLAY` unset; activation env set via `dbus-update-activation-environment` **before** `exec gnome-shell`.
- `engine.py` and `styx_agent.py` must each end this plan under 500 lines.
- Agent version string: `0.5.0`.
- Old stream-setting keys `h264_crf`, `h264_streaming_mode`, `h264_paintover_crf` stay honored.
- Backend sends 2.0-only keys only to agents reporting `agent_version >= 0.5.0`.
- Semantic commits (`feat(agent): …`, `fix(backend): …`), each ending with
  `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Commands: backend tests `cd backend && .venv/bin/python -m pytest -q`; agent tests `cd agent && ../backend/.venv/bin/python -m pytest tests -q`; lint `cd backend && .venv/bin/python -m ruff check app/ tests/ ../agent`.

## Deliberate simplifications vs spec (approved intent, smaller diff)

- **No DB data migration for the `h264_*` → `video_*` rename.** The backend resolver emits `video_*` (aliasing old keys on read); the frontend keeps writing `h264_*` until Phase 1 redoes the quality UI. Same compatibility, zero migration.
- **Video-frame detection stays "binary and not `0x01`"** instead of "`0x04` only": JPEG/striped fallback frames use other type bytes and must also disarm the watchdog.
- **`doctor --grant` success check is the restore-token file** (no PNG screenshot); screenshot capture needs PipeWire/GStreamer bindings the agent venv lacks.

## Review Focus

1. Agent upgraded in place over a 0.4.11 `config.json` (has `seat_socket_index`, `mode`, old `stream_settings`) must start without KeyError → Task 7 test `test_run_config_from_0411_is_accepted`.
2. A stream-settings change that only touches quality must restart selkies but **not** the GNOME seat (open apps survive) → Task 7 test `test_settings_change_keeps_gnome_seat`.
3. Box with no physical X display (headless server) running `doctor --grant --local` must fail with a clear message, not hang → Task 8 test `test_grant_local_without_display_errors`.
4. Viewer connected while the seat restarts: gateway must return 502 then recover on reconnect, not crash → Task 5 test `test_ws_proxy_upstream_down_returns_502`.
5. Workstation stream_settings with junk types (`"video_crf": "abc"`) must not break launch → Task 3 test `test_quality_env_ignores_bad_values`.

---

## File Structure

| File | Change | Responsibility |
|---|---|---|
| `backend/app/services/ws_settings.py` | Create | `resolve_stream_settings()` — single resolver |
| `backend/app/services/settings_store.py` | Modify | 3 new specs (seat size, cursor workaround) |
| `backend/app/routers/agent.py` | Modify | Use resolver; drop inline idle folding |
| `backend/app/services/artifacts.py`, `backend/app/routers/enroll.py`, `backend/app/services/workstations.py` | Modify | Artifact + agent-file lists for 0.5.0 |
| `agent/engine.py` | Modify | selkies 2.0 argv/env builder; remove launcher/control-port |
| `agent/seat_gnome.py` | Create | Headless GNOME session: launch script, start, readiness, stop |
| `agent/seat_labwc.py` | Create | Moved labwc shell + clipboard-bridge start helpers (from `styx_agent.run`) |
| `agent/health.py` | Create | Moved gw-state readers + health payload (from `styx_agent.py`) |
| `agent/gateway.py` | Modify | Single-upstream proxy, cursor workaround inject |
| `agent/styx_agent.py` | Modify | Supervisor wiring for gnome seat, escalation, consent state, `grant`, `rollback`, 0.5.0 |
| `agent/grant.py` | Create | `doctor --grant` consent flow |
| `agent/selkies_launcher.py` | Delete | 2.0 binds loopback natively |
| `agent/enroll.sh` | Modify | File list, wheel pins, `--upgrade` mode with `.prev` backup |
| `scripts/build_agent_artifacts.sh` | Modify | PyPI pins; drop web dist + libshim |
| `docs/` pages, `backend/app/config.py:58`, `backend/app/services/artifacts.py:7` | Modify | Docs + stale comments |

---

### Task 1: Prove virtual-monitor resize and headless consent dialog (spike, no product code)

Decides whether Task 9 implements live resize, and whether Task 8 can auto-accept. Run on the EliteMini as the logged-in user. Everything lives in the scratch dir and is deleted after.

**Files:** none committed. Record results in the plan file under "Task 1 results".

- [ ] **Step 1: Start a headless GNOME with a clean env**

```bash
mkdir -p ~/spike1 && cd ~/spike1
cat > gnome.sh <<'EOF'
#!/bin/bash
unset DISPLAY WAYLAND_DISPLAY
export XDG_SESSION_TYPE=wayland XDG_CURRENT_DESKTOP=ubuntu:GNOME GNOME_SHELL_SESSION_MODE=ubuntu
dbus-update-activation-environment DISPLAY= WAYLAND_DISPLAY=styx-proof-0 XDG_SESSION_TYPE=wayland XDG_CURRENT_DESKTOP=ubuntu:GNOME
echo "$DBUS_SESSION_BUS_ADDRESS" > "$(dirname "$0")/bus.addr"
exec gnome-shell --headless --wayland --no-x11 --virtual-monitor 1920x1080 --wayland-display=styx-proof-0
EOF
chmod +x gnome.sh
env -u DISPLAY -u WAYLAND_DISPLAY nohup dbus-run-session -- ./gnome.sh > gnome.log 2>&1 &
sleep 10; ls /run/user/$(id -u)/styx-proof-0
```

Expected: socket exists.

- [ ] **Step 2: Read the monitor config and try a new mode**

```bash
export DBUS_SESSION_BUS_ADDRESS=$(cat ~/spike1/bus.addr)
gdbus call --session -d org.gnome.Mutter.DisplayConfig -o /org/gnome/Mutter/DisplayConfig \
  -m org.gnome.Mutter.DisplayConfig.GetCurrentState > state.txt
grep -oE "'[0-9]+x[0-9]+@[0-9.]+'" state.txt | sort -u | head
```

Expected: a serial number and at least one mode id like `'1920x1080@60.000'`. If more than one mode is listed, apply a different one (replace SERIAL, CONNECTOR from state.txt, MODE):

```bash
gdbus call --session -d org.gnome.Mutter.DisplayConfig -o /org/gnome/Mutter/DisplayConfig \
  -m org.gnome.Mutter.DisplayConfig.ApplyMonitorsConfig SERIAL 1 \
  "[(0, 0, 1.0, uint32 0, true, [('CONNECTOR', 'MODE', @a{sv} {})])]" "@a{sv} {}"
```

- [ ] **Step 3: Test unattended consent**

```bash
cd ~/spike1 && python3 -m venv venv && venv/bin/pip -q install selkies==2.0.0
mv ~/.local/state/pixelflux/portal-restore-token ~/spike1/token.bak 2>/dev/null || true
export DBUS_SESSION_BUS_ADDRESS=$(cat ~/spike1/bus.addr)
env -u DISPLAY venv/bin/selkies --port=8099 --enable-basic-auth=false --wayland=true \
  --wayland-host-display=styx-proof-0 > selkies.log 2>&1 &
sleep 6
# open http://127.0.0.1:8099 in a browser ON THIS BOX (starts the portal request), then:
sleep 5
S=$(gdbus call --session -d org.gnome.Mutter.RemoteDesktop -o /org/gnome/Mutter/RemoteDesktop \
     -m org.gnome.Mutter.RemoteDesktop.CreateSession | grep -oE "/[^']+")
gdbus call --session -d org.gnome.Mutter.RemoteDesktop -o "$S" -m org.gnome.Mutter.RemoteDesktop.Session.Start
for st in true false; do gdbus call --session -d org.gnome.Mutter.RemoteDesktop -o "$S" \
  -m org.gnome.Mutter.RemoteDesktop.Session.NotifyKeyboardKeysym 65293 $st; done
sleep 5; ls -la ~/.local/state/pixelflux/portal-restore-token
```

- [ ] **Step 4: Record the decision**

Append to this plan under a new heading `## Task 1 results`:
- `RESIZE=live` if Step 2 listed ≥ 2 modes and the apply call succeeded; otherwise `RESIZE=fixed`.
- `CONSENT=auto` if Step 3's `ls` shows a freshly written token; otherwise `CONSENT=local`. If `CONSENT=local`, restore the old token: `mv ~/spike1/token.bak ~/.local/state/pixelflux/portal-restore-token`.

- [ ] **Step 5: Clean up**

```bash
kill $(ps -eo pid,comm,args | awk '($2=="gnome-shell" && /styx-proof-0/) || ($2=="selkies" && /8099/) {print $1}'); rm -rf ~/spike1
```

---

### Task 2: Backend settings resolver

**Files:**
- Create: `backend/app/services/ws_settings.py`
- Modify: `backend/app/services/settings_store.py` (append 3 specs after `WORKSTATION_OFFLINE_AFTER_S` spec, ~line 82)
- Modify: `backend/app/config.py:66-71` (3 defaults)
- Modify: `backend/app/routers/agent.py:68-79,102-111`
- Test: `backend/tests/test_ws_settings.py`, `backend/tests/test_workstation_agent_api.py`

**Interfaces:**
- Produces: `resolve_stream_settings(ws_ss: dict | None, sys: Mapping[str, Any], agent_version: str | None) -> dict` — effective settings dict sent to the agent.
- Produces: `is_v2_agent(agent_version: str | None) -> bool`.
- Effective keys always present: `idle_timeout_s`, `idle_warn_lead_s`, `idle_timeout_enabled`. For v2 agents also: `seat_shell` (`"gnome"`|`"labwc"`), `seat_width`, `seat_height`, `cursor_workaround`, and `video_crf` / `video_streaming_mode` / `video_paintover_crf` when an old or new key is set.

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_ws_settings.py
from app.services.ws_settings import is_v2_agent, resolve_stream_settings

SYS = {"WORKSTATION_IDLE_TIMEOUT_S": 900, "WORKSTATION_IDLE_WARN_LEAD_S": 60,
       "WORKSTATION_IDLE_TIMEOUT_ENABLED": True, "WORKSTATION_SEAT_WIDTH": 2560,
       "WORKSTATION_SEAT_HEIGHT": 1440, "WORKSTATION_CURSOR_WORKAROUND": True}


def test_is_v2_agent():
    assert is_v2_agent("0.5.0") and is_v2_agent("0.6.2") and is_v2_agent("1.0.0")
    assert not is_v2_agent("0.4.11") and not is_v2_agent(None) and not is_v2_agent("junk")


def test_defaults_fill_and_overrides_win():
    eff = resolve_stream_settings({"framerate": 60, "idle_timeout_s": 300}, SYS, "0.5.0")
    assert eff["framerate"] == 60
    assert eff["idle_timeout_s"] == 300            # override wins
    assert eff["idle_warn_lead_s"] == 60           # default fills
    assert eff["seat_shell"] == "gnome"
    assert (eff["seat_width"], eff["seat_height"]) == (2560, 1440)
    assert eff["cursor_workaround"] is True


def test_old_h264_keys_alias_to_video_keys_for_v2():
    eff = resolve_stream_settings({"h264_crf": 22, "h264_streaming_mode": True,
                                   "h264_paintover_crf": 18}, SYS, "0.5.0")
    assert eff["video_crf"] == 22
    assert eff["video_streaming_mode"] is True
    assert eff["video_paintover_crf"] == 18


def test_new_video_key_beats_old_alias():
    eff = resolve_stream_settings({"h264_crf": 22, "video_crf": 30}, SYS, "0.5.0")
    assert eff["video_crf"] == 30


def test_v1_agent_gets_todays_shape_only():
    eff = resolve_stream_settings({"h264_crf": 22}, SYS, "0.4.11")
    assert eff["h264_crf"] == 22
    for k in ("seat_shell", "seat_width", "cursor_workaround", "video_crf"):
        assert k not in eff
    assert eff["idle_timeout_s"] == 900


def test_bad_seat_shell_falls_back_to_gnome():
    eff = resolve_stream_settings({"seat_shell": "kde"}, SYS, "0.5.0")
    assert eff["seat_shell"] == "gnome"
```

Add to `backend/tests/test_workstation_agent_api.py`:

```python
@pytest.mark.asyncio
async def test_heartbeat_v2_agent_gets_seat_keys(client, session):
    await _make_ws(session, status="online")
    r = await client.post("/api/agent/heartbeat",
                          json={"status": "online", "health": {"agent_version": "0.5.0"}},
                          headers=_auth())
    ss = r.json()["stream_settings"]
    assert ss["seat_shell"] == "gnome" and ss["cursor_workaround"] is True


@pytest.mark.asyncio
async def test_heartbeat_v1_agent_gets_no_seat_keys(client, session):
    await _make_ws(session, status="online")
    r = await client.post("/api/agent/heartbeat",
                          json={"status": "online", "health": {"agent_version": "0.4.11"}},
                          headers=_auth())
    assert "seat_shell" not in r.json()["stream_settings"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && .venv/bin/python -m pytest tests/test_ws_settings.py tests/test_workstation_agent_api.py -q`
Expected: FAIL — `ModuleNotFoundError: app.services.ws_settings`.

- [ ] **Step 3: Implement**

```python
# backend/app/services/ws_settings.py
"""Single resolver for the stream_settings delivered to workstation agents:
per-workstation override (ws.stream_settings) over system default."""
from collections.abc import Mapping
from typing import Any

# old key -> 2.0 key; old keys stay honored (frontend writes them until Phase 1)
_VIDEO_ALIASES = {"h264_crf": "video_crf",
                  "h264_streaming_mode": "video_streaming_mode",
                  "h264_paintover_crf": "video_paintover_crf"}
_SEAT_SHELLS = ("gnome", "labwc")


def is_v2_agent(agent_version: str | None) -> bool:
    try:
        major, minor = (int(x) for x in (agent_version or "").split(".")[:2])
    except ValueError:
        return False
    return (major, minor) >= (0, 5)


def resolve_stream_settings(ws_ss: dict | None, sys: Mapping[str, Any],
                            agent_version: str | None) -> dict:
    ss = dict(ws_ss or {})
    eff = {**ss,
           "idle_timeout_s": ss.get("idle_timeout_s", sys.get("WORKSTATION_IDLE_TIMEOUT_S")),
           "idle_warn_lead_s": ss.get("idle_warn_lead_s", sys.get("WORKSTATION_IDLE_WARN_LEAD_S")),
           "idle_timeout_enabled": ss.get("idle_timeout_enabled",
                                          sys.get("WORKSTATION_IDLE_TIMEOUT_ENABLED"))}
    if not is_v2_agent(agent_version):
        return eff
    for old, new in _VIDEO_ALIASES.items():
        if new not in eff and old in eff:
            eff[new] = eff[old]
    shell = ss.get("seat_shell")
    eff["seat_shell"] = shell if shell in _SEAT_SHELLS else "gnome"
    eff["seat_width"] = ss.get("seat_width", sys.get("WORKSTATION_SEAT_WIDTH"))
    eff["seat_height"] = ss.get("seat_height", sys.get("WORKSTATION_SEAT_HEIGHT"))
    eff["cursor_workaround"] = ss.get("cursor_workaround",
                                      sys.get("WORKSTATION_CURSOR_WORKAROUND"))
    return eff
```

`backend/app/config.py` — after `WORKSTATION_IDLE_TIMEOUT_ENABLED: bool = True` add:

```python
    WORKSTATION_SEAT_WIDTH: int = 2560
    WORKSTATION_SEAT_HEIGHT: int = 1440
    WORKSTATION_CURSOR_WORKAROUND: bool = True
```

`backend/app/services/settings_store.py` — after the `WORKSTATION_OFFLINE_AFTER_S` spec add:

```python
    _spec("WORKSTATION_SEAT_WIDTH", "workstation_features", "Seat width (px)",
          "Default headless GNOME seat width.", "int",
          "WORKSTATION_SEAT_WIDTH", min=800, max=7680),
    _spec("WORKSTATION_SEAT_HEIGHT", "workstation_features", "Seat height (px)",
          "Default headless GNOME seat height.", "int",
          "WORKSTATION_SEAT_HEIGHT", min=600, max=4320),
    _spec("WORKSTATION_CURSOR_WORKAROUND", "workstation_features",
          "Hide browser cursor over stream",
          "Use only the in-video cursor (fixes double/stale cursor on GNOME seats).",
          "bool", "WORKSTATION_CURSOR_WORKAROUND"),
```

`backend/app/routers/agent.py` — add import `from app.services.ws_settings import resolve_stream_settings`. Replace lines computing `ss`, `idle_timeout`, `idle_lead`, `idle_enabled` (≈68-79) with:

```python
    effective_ss = resolve_stream_settings(ws.stream_settings, _sys_settings,
                                           ws.agent_version)
    idle_timeout = effective_ss["idle_timeout_s"]
    idle_enabled = effective_ss["idle_timeout_enabled"]
```

and delete the later `effective_ss = {**(ws.stream_settings or {}), ...}` block (≈102-108) and its comment. If `_sys_settings` has no `__getitem__`/`get` mapping semantics, pass `{k: _sys_settings.get(k) for k in (...)}` — check `settings_store.settings.get` signature first (it is used with `.get(key)` today).

- [ ] **Step 4: Run tests**

Run: `cd backend && .venv/bin/python -m pytest -q`
Expected: all pass (≥ 484 + 8 new).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/ws_settings.py backend/app/services/settings_store.py backend/app/config.py backend/app/routers/agent.py backend/tests/test_ws_settings.py backend/tests/test_workstation_agent_api.py
git commit -m "feat(backend): single stream-settings resolver with v2 seat keys"
```

---

### Task 3: Agent engine — selkies 2.0 command builder

**Files:**
- Modify: `agent/engine.py:443-536` (replace `build_selkies_cmd`)
- Test: `agent/tests/test_engine.py` (replace tests at lines 29-92 and 457+ that assert old flags)

**Interfaces:**
- Consumes: effective `stream_settings` keys from Task 2.
- Produces: `build_selkies_cmd(cfg: dict, internal_port: int, seat: dict | None = None) -> tuple[list[str], dict]`. `seat` for a GNOME seat is `{"socket": "styx-seat-0", "bus": "<DBUS_SESSION_BUS_ADDRESS>"}`; `None` means labwc seat (`cfg["mode"]=="seat"`) or mirror.
- Produces: `SELKIES_FLAG_NAMES_FILE` not needed — test reads the installed wheel.

- [ ] **Step 1: Write the failing tests** (replace the five old `*_cmd_*` tests and `test_build_selkies_cmd_maps_gaming_knobs`)

```python
def _flags(cmd):
    return {a.split("=", 1)[0] for a in cmd if a.startswith("--")}


def test_mirror_cmd_is_x11_with_fixed_size(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    monkeypatch.setattr(engine, "pick_dri_node", lambda: "/dev/dri/renderD128")
    monkeypatch.setattr(engine, "resolve_monitor_source", lambda: "out.monitor")
    monkeypatch.setattr(engine, "_find_xauthority", lambda c: "/tmp/xa")
    monkeypatch.setattr(engine, "query_display_geometry", lambda d, x: (2560, 1440))
    cmd, env = engine.build_selkies_cmd(cfg, 18444)
    assert cmd[0].endswith("venv/bin/selkies")
    assert "--port=18444" in cmd and "--enable-basic-auth=false" in cmd
    assert "--manual-width=2560" in cmd and "--manual-height=1440" in cmd
    assert "--encode-dri=/dev/dri/renderD128" in cmd and "--render-dri=/dev/dri/renderD128" in cmd
    assert "--wayland=true" not in cmd
    assert env["DISPLAY"] == ":1" and env["XAUTHORITY"] == "/tmp/xa"
    assert "--control-port" not in _flags(cmd) and "--dri-node" not in _flags(cmd)
    assert not any("pw" in a for a in cmd)


def test_gnome_seat_cmd_targets_host_display(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, mode="seat", display="")
    monkeypatch.setattr(engine, "pick_dri_node", lambda: "/dev/dri/renderD128")
    monkeypatch.setattr(engine, "resolve_monitor_source", lambda: "x.monitor")
    seat = {"socket": "styx-seat-0", "bus": "unix:path=/tmp/bus"}
    cmd, env = engine.build_selkies_cmd(cfg, 18444, seat)
    assert "--wayland=true" in cmd
    assert "--wayland-host-display=styx-seat-0" in cmd
    assert env["DBUS_SESSION_BUS_ADDRESS"] == "unix:path=/tmp/bus"
    assert env["XDG_CURRENT_DESKTOP"] == "ubuntu:GNOME"
    assert "DISPLAY" not in env and "WAYLAND_DISPLAY" not in env
    assert "--audio-device-name=styx-seat.monitor" in cmd


def test_labwc_seat_cmd_uses_own_compositor(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, mode="seat", display="")
    monkeypatch.setattr(engine, "pick_dri_node", lambda: "")
    monkeypatch.setattr(engine, "resolve_monitor_source", lambda: "")
    cmd, env = engine.build_selkies_cmd(cfg, 18444)
    assert "--wayland=true" in cmd
    assert not any(a.startswith("--wayland-host-display") for a in cmd)
    assert "SELKIES_USE_CPU" not in env and env["SELKIES_AUDIO_ENABLED"] == "false"


def test_features_off_until_their_phase(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    monkeypatch.setattr(engine, "pick_dri_node", lambda: "")
    monkeypatch.setattr(engine, "resolve_monitor_source", lambda: "")
    monkeypatch.setattr(engine, "_find_xauthority", lambda c: None)
    monkeypatch.setattr(engine, "query_display_geometry", lambda d, x: (1920, 1080))
    cmd, _ = engine.build_selkies_cmd(cfg, 1)
    for f in ("--printing-enabled=false", "--microphone-enabled=false",
              "--webcam-enabled=false", "--gamepad-enabled=false"):
        assert f in cmd


def test_quality_env_prefers_video_keys_and_keeps_old(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, stream_settings={"h264_crf": 22, "video_paintover_crf": 18,
                                          "video_streaming_mode": True})
    for fn, v in (("pick_dri_node", ""), ("resolve_monitor_source", "")):
        monkeypatch.setattr(engine, fn, lambda *a, _v=v: _v)
    monkeypatch.setattr(engine, "_find_xauthority", lambda c: None)
    monkeypatch.setattr(engine, "query_display_geometry", lambda d, x: (1920, 1080))
    _, env = engine.build_selkies_cmd(cfg, 1)
    assert env["SELKIES_VIDEO_CRF"] == "22"
    assert env["SELKIES_VIDEO_PAINTOVER_CRF"] == "18"
    assert env["SELKIES_VIDEO_STREAMING_MODE"] == "true"


def test_quality_env_ignores_bad_values(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, stream_settings={"video_crf": "abc", "video_paintover_crf": 999})
    for fn, v in (("pick_dri_node", ""), ("resolve_monitor_source", "")):
        monkeypatch.setattr(engine, fn, lambda *a, _v=v: _v)
    monkeypatch.setattr(engine, "_find_xauthority", lambda c: None)
    monkeypatch.setattr(engine, "query_display_geometry", lambda d, x: (1920, 1080))
    _, env = engine.build_selkies_cmd(cfg, 1)
    assert "SELKIES_VIDEO_CRF" not in env and "SELKIES_VIDEO_PAINTOVER_CRF" not in env
    assert env["SELKIES_VIDEO_STREAMING_MODE"] == "false"   # 2.0 default is true; keep ours


def test_every_flag_exists_in_installed_selkies(tmp_path, monkeypatch):
    """2.0 only WARNS on unknown flags, so a renamed flag would silently no-op."""
    import importlib.util, re
    spec = importlib.util.find_spec("selkies")
    if spec is None or not spec.submodule_search_locations:
        pytest.skip("selkies 2.0 not installed in this venv")
    src = Path(list(spec.submodule_search_locations)[0], "settings.py").read_text()
    known = set(re.findall(r'"name":\s*"([a-z0-9_]+)"', src))
    cfg = _cfg(tmp_path, mode="seat", display="")
    monkeypatch.setattr(engine, "pick_dri_node", lambda: "/dev/dri/renderD128")
    monkeypatch.setattr(engine, "resolve_monitor_source", lambda: "m")
    cmd, _ = engine.build_selkies_cmd(cfg, 1, {"socket": "s", "bus": "b"})
    for flag in _flags(cmd):
        assert flag[2:].replace("-", "_") in known, flag
```

Add `import pytest` and `from pathlib import Path` at the top of the test file if missing. Remove `(install / "web").mkdir()` from `_cfg` is NOT needed (harmless).

- [ ] **Step 2: Run to verify failure**

Run: `cd agent && ../backend/.venv/bin/python -m pytest tests/test_engine.py -q`
Expected: FAIL (`build_selkies_cmd() takes 3 positional arguments`, missing `--enable-basic-auth=false`, etc.).

- [ ] **Step 3: Replace `build_selkies_cmd`**

```python
def build_selkies_cmd(cfg: dict, internal_port: int,
                      seat: dict | None = None) -> tuple[list[str], dict]:
    """argv + env for selkies 2.0. Secrets travel via env, never argv.

    seat: {"socket", "bus"} of a headless GNOME seat (host capture via the
    portal), or None for the labwc seat (pixelflux's own compositor) / mirror.
    Mirror mode queries the live X display and may raise; the supervisor reports it.
    """
    install = Path(cfg["install_dir"])
    s = cfg.get("stream_settings", {})
    env = {
        "HOME": str(HOME),
        "XDG_RUNTIME_DIR": os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}"),
        "PYTHONNOUSERSITE": "1",
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "FILE_MANAGER_PATH": os.environ.get("FILE_MANAGER_PATH", str(HOME / "Downloads")),
    }
    cmd = [
        str(install / "venv/bin/selkies"),
        f"--port={internal_port}",          # 2.0 binds loopback by default
        "--enable-basic-auth=false",        # gateway owns auth
        "--mode=websockets",
        "--encoder=h264enc",
        f"--framerate={s.get('framerate', 60)}",
        "--second-screen=false",
        # Off until their phase ships (spec §6): devices, printing.
        "--printing-enabled=false", "--microphone-enabled=false",
        "--webcam-enabled=false", "--gamepad-enabled=false",
    ]
    dri = pick_dri_node()
    if dri:
        cmd += [f"--encode-dri={dri}", f"--render-dri={dri}"]
        # Client pushes use_cpu=true; "|locked" keeps the GPU encoder on.
        env["SELKIES_USE_CPU"] = "false|locked"

    if seat is not None:                     # headless GNOME seat
        cmd += ["--wayland=true", f"--wayland-host-display={seat['socket']}"]
        env.update({"DBUS_SESSION_BUS_ADDRESS": seat["bus"],
                    "XDG_CURRENT_DESKTOP": "ubuntu:GNOME",
                    "XDG_SESSION_TYPE": "wayland"})
        monitor = f"{SEAT_SINK}.monitor"
    elif cfg.get("mode") == "seat":          # labwc seat (fallback)
        cmd.append("--wayland=true")
        monitor = resolve_monitor_source()
    else:                                    # mirror
        env["DISPLAY"] = cfg["display"]
        xauth = _find_xauthority(cfg)
        if xauth:
            env["XAUTHORITY"] = xauth
        w, h = query_display_geometry(cfg["display"], xauth)
        cmd += [f"--manual-width={w}", f"--manual-height={h}"]
        monitor = resolve_monitor_source()

    # Quality knobs: 2.0 names, old h264_* keys still honored (spec §4).
    crf = _int_in(s.get("video_crf", s.get("h264_crf")), 5, 50)
    if crf is not None:
        env["SELKIES_VIDEO_CRF"] = str(crf)
    streaming = s.get("video_streaming_mode", s.get("h264_streaming_mode"))
    # 2.0 defaults streaming mode ON; keep today's default (off) unless asked.
    env["SELKIES_VIDEO_STREAMING_MODE"] = "true" if streaming is True else "false"
    if s.get("use_paint_over_quality") is False:
        env["SELKIES_USE_PAINT_OVER_QUALITY"] = "false"
    pcrf = _int_in(s.get("video_paintover_crf", s.get("h264_paintover_crf")), 5, 50)
    if pcrf is not None:
        env["SELKIES_VIDEO_PAINTOVER_CRF"] = str(pcrf)

    if monitor:
        env["SELKIES_AUDIO_ENABLED"] = "true"
        cmd.append(f"--audio-device-name={monitor}")
    else:
        env["SELKIES_AUDIO_ENABLED"] = "false"
    return cmd, env
```

Check `_int_in` returns None for non-int input (`"abc"`); if it raises, wrap: `try: int(value) except (TypeError, ValueError): return None` inside `_int_in`.

- [ ] **Step 4: Run tests**

Run: `cd agent && ../backend/.venv/bin/python -m pytest tests/test_engine.py -q`
Expected: PASS (flag-existence test SKIPPED locally unless selkies 2.0 is installed; it runs on the box in Task 11).

- [ ] **Step 5: Commit**

```bash
git add agent/engine.py agent/tests/test_engine.py
git commit -m "feat(agent): build selkies 2.0 command line (host capture, new flags)"
```

---

### Task 4: `seat_gnome.py` — headless GNOME session

**Files:**
- Create: `agent/seat_gnome.py`
- Test: `agent/tests/test_seat_gnome.py`

**Interfaces:**
- Produces: `SOCKET = "styx-seat-0"`
- Produces: `build_launch_script(width: int, height: int, sink: str, bus_file: str) -> str`
- Produces: `gnome_available() -> tuple[bool, str]` — `(ok, reason)`; ok when `gnome-shell` exists and major version ≥ 46.
- Produces: `class GnomeSeat(install_dir: Path, runtime_dir: str, log)` with `start(width: int, height: int) -> None`, `ready(timeout: float = 20) -> bool`, `alive() -> bool`, `stop() -> None`, attributes `bus: str | None`, `restarts: int`, and `info() -> dict` returning `{"socket": SOCKET, "bus": self.bus}` for `engine.build_selkies_cmd`.

- [ ] **Step 1: Write the failing tests**

```python
# agent/tests/test_seat_gnome.py
import subprocess
from pathlib import Path

import seat_gnome


def test_launch_script_scrubs_display_and_sets_activation_env_before_exec():
    s = seat_gnome.build_launch_script(2560, 1440, "styx-seat", "/tmp/bus")
    lines = s.splitlines()
    unset = next(i for i, l in enumerate(lines) if l.startswith("unset DISPLAY WAYLAND_DISPLAY"))
    act = next(i for i, l in enumerate(lines) if l.startswith("dbus-update-activation-environment"))
    exe = next(i for i, l in enumerate(lines) if l.startswith("exec gnome-shell"))
    assert unset < act < exe
    assert "DISPLAY=" in lines[act] and "WAYLAND_DISPLAY=styx-seat-0" in lines[act]
    assert "PULSE_SINK=styx-seat" in lines[act]
    assert "export PULSE_SINK=styx-seat" in s
    assert "--virtual-monitor 2560x1440" in lines[exe]
    assert "--wayland-display=styx-seat-0" in lines[exe]
    assert "--unsafe-mode" not in s
    assert '> "/tmp/bus"' in s


def test_gnome_available_version_gate(monkeypatch):
    monkeypatch.setattr(seat_gnome.shutil, "which", lambda n: "/usr/bin/gnome-shell")
    for out, ok in (("GNOME Shell 46.0\n", True), ("GNOME Shell 47.2\n", True),
                    ("GNOME Shell 45.3\n", False)):
        monkeypatch.setattr(seat_gnome.subprocess, "run",
                            lambda *a, _o=out, **k: subprocess.CompletedProcess(a, 0, _o, ""))
        assert seat_gnome.gnome_available()[0] is ok
    monkeypatch.setattr(seat_gnome.shutil, "which", lambda n: None)
    assert seat_gnome.gnome_available() == (False, "gnome-shell not installed")


def test_ready_needs_socket_and_bus(tmp_path, monkeypatch):
    seat = seat_gnome.GnomeSeat(tmp_path, str(tmp_path), log=subprocess.DEVNULL)
    seat._proc = type("P", (), {"poll": lambda self: None})()
    (tmp_path / "gnome-bus.addr").write_text("unix:path=/x\n")
    monkeypatch.setattr(seat, "_shell_answers", lambda: True)
    assert seat.ready(timeout=0.2) is False          # no socket yet
    (tmp_path / seat_gnome.SOCKET).touch()
    assert seat.ready(timeout=0.2) is True
    assert seat.info() == {"socket": "styx-seat-0", "bus": "unix:path=/x"}


def test_start_writes_script_and_counts_restarts(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(seat_gnome.subprocess, "Popen",
                        lambda cmd, **k: calls.append((cmd, k)) or object())
    seat = seat_gnome.GnomeSeat(tmp_path, str(tmp_path), log=subprocess.DEVNULL)
    seat.start(1920, 1080)
    seat.start(1920, 1080)
    assert seat.restarts == 1
    cmd, kw = calls[0]
    assert cmd[:2] == ["dbus-run-session", "--"]
    assert Path(cmd[2]).read_text().startswith("#!/bin/bash")
    assert "DISPLAY" not in kw["env"] and "WAYLAND_DISPLAY" not in kw["env"]
```

- [ ] **Step 2: Run to verify failure**

Run: `cd agent && ../backend/.venv/bin/python -m pytest tests/test_seat_gnome.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'seat_gnome'`.

- [ ] **Step 3: Implement**

```python
# agent/seat_gnome.py
"""Headless GNOME seat: a real gnome-shell on its own session bus, captured by
selkies 2.0 through xdg-desktop-portal (spec §5.1).

The activation env MUST be set before anything can activate a portal: an
inherited DISPLAY makes the consent dialog appear on the physical desktop."""
import os
import re
import shutil
import subprocess
import time
from pathlib import Path

SOCKET = "styx-seat-0"
MIN_GNOME = 46
_SCRUB = ("DISPLAY", "WAYLAND_DISPLAY", "XAUTHORITY", "DBUS_SESSION_BUS_ADDRESS",
          "XDG_SESSION_ID", "GNOME_SETUP_DISPLAY", "SESSION_MANAGER")


def build_launch_script(width: int, height: int, sink: str, bus_file: str) -> str:
    return "\n".join([
        "#!/bin/bash",
        "# generated by styx-agent: headless GNOME seat (do not edit)",
        "unset DISPLAY WAYLAND_DISPLAY XAUTHORITY",
        "export XDG_SESSION_TYPE=wayland XDG_CURRENT_DESKTOP=ubuntu:GNOME "
        "XDG_SESSION_DESKTOP=ubuntu GNOME_SHELL_SESSION_MODE=ubuntu",
        f"export PULSE_SINK={sink}",
        f"dbus-update-activation-environment DISPLAY= WAYLAND_DISPLAY={SOCKET} "
        f"XDG_SESSION_TYPE=wayland XDG_CURRENT_DESKTOP=ubuntu:GNOME PULSE_SINK={sink}",
        f'echo "$DBUS_SESSION_BUS_ADDRESS" > "{bus_file}"',
        f"exec gnome-shell --headless --wayland --no-x11 "
        f"--virtual-monitor {width}x{height} --wayland-display={SOCKET}",
        "",
    ])


def gnome_available() -> tuple[bool, str]:
    if not shutil.which("gnome-shell"):
        return False, "gnome-shell not installed"
    try:
        out = subprocess.run(["gnome-shell", "--version"], capture_output=True,
                             text=True, timeout=10).stdout
    except (OSError, subprocess.TimeoutExpired) as e:
        return False, f"gnome-shell --version failed: {e}"
    m = re.search(r"(\d+)\.", out)
    if not m or int(m.group(1)) < MIN_GNOME:
        return False, f"GNOME Shell {MIN_GNOME}+ required (found: {out.strip()})"
    return True, ""


class GnomeSeat:
    def __init__(self, install_dir: Path, runtime_dir: str, log):
        self.install_dir = Path(install_dir)
        self.runtime_dir = runtime_dir
        self.log = log
        self.bus_file = self.install_dir / "gnome-bus.addr"
        self.script = self.install_dir / "gnome-seat.sh"
        self.bus: str | None = None
        self.restarts = 0
        self._proc = None
        self._started = False

    def start(self, width: int, height: int) -> None:
        from engine import SEAT_SINK
        if self._started:
            self.restarts += 1
        self._started = True
        self.bus = None
        self.bus_file.unlink(missing_ok=True)
        self.script.write_text(build_launch_script(width, height, SEAT_SINK,
                                                   str(self.bus_file)))
        self.script.chmod(0o700)
        env = {k: v for k, v in os.environ.items() if k not in _SCRUB}
        self._proc = subprocess.Popen(["dbus-run-session", "--", str(self.script)],
                                      env=env, stdout=self.log, stderr=self.log)

    def _shell_answers(self) -> bool:
        r = subprocess.run(
            ["gdbus", "call", "--session", "-d", "org.gnome.Shell", "-o",
             "/org/gnome/Shell", "-m", "org.freedesktop.DBus.Peer.Ping"],
            env={**os.environ, "DBUS_SESSION_BUS_ADDRESS": self.bus or ""},
            capture_output=True, timeout=5)
        return r.returncode == 0

    def ready(self, timeout: float = 20) -> bool:
        deadline = time.time() + timeout
        while time.time() < deadline:
            if not self.alive():
                return False
            if self.bus is None and self.bus_file.exists():
                self.bus = self.bus_file.read_text().strip() or None
            if (self.bus and Path(self.runtime_dir, SOCKET).exists()
                    and self._shell_answers()):
                return True
            time.sleep(0.1)
        return False

    def alive(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def info(self) -> dict:
        return {"socket": SOCKET, "bus": self.bus}

    def stop(self) -> None:
        p = self._proc
        if p is not None and p.poll() is None:
            p.terminate()
            try:
                p.wait(timeout=15)
            except subprocess.TimeoutExpired:
                p.kill()
        self._proc = None
```

In `test_start_writes_script_and_counts_restarts`, the fake Popen returns `object()`; `start` does not call methods on it, so this works.

- [ ] **Step 4: Run tests**

Run: `cd agent && ../backend/.venv/bin/python -m pytest tests/test_seat_gnome.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add agent/seat_gnome.py agent/tests/test_seat_gnome.py
git commit -m "feat(agent): headless GNOME seat session (scrubbed env, readiness)"
```

---

### Task 5: Gateway — single upstream + cursor workaround

**Files:**
- Modify: `agent/gateway.py:158-369` (`create_app`, `main`)
- Modify: `agent/styx_agent.py:79-97` (`build_gateway_cmd`)
- Test: `agent/tests/test_gateway.py`, `agent/tests/test_gateway_idle.py`, `agent/tests/test_styx_agent.py`

**Interfaces:**
- Produces: `create_app(user: str, password: str, upstream_port: int, files_dir: str = "", state_file: str = "", idle_timeout_s: int = 0, idle_lead_s: int = 60, idle_enabled: bool = False, cursor_workaround: bool = False) -> web.Application` (the `web_dir` first parameter is **removed**).
- Produces: `inject_cursor_hide(html: str, enabled: bool) -> str`.
- Gateway CLI: `gateway.py <listen_port> <upstream_port>`; env adds `STYX_GW_CURSOR_WORKAROUND` (`"1"` = on).

- [ ] **Step 1: Update existing tests to the new signature**

In `agent/tests/test_gateway.py` and `agent/tests/test_gateway_idle.py` replace every
`gateway.create_app(str(tmp_path), "styx", "pw",` with `gateway.create_app("styx", "pw",`. Tests that wrote `tmp_path / "index.html"` and expected the gateway to serve it must instead serve that HTML from the fake upstream (`upstream.router.add_get("/", lambda r: web.Response(text="<html><head><title>x</title></head><body></body></html>", content_type="text/html"))`).

- [ ] **Step 2: Write the new failing tests** (append to `agent/tests/test_gateway.py`)

```python
async def _upstream_app():
    from aiohttp import web
    app = web.Application()
    page = "<html><head><title>Selkies</title></head><body>x</body></html>"
    app.router.add_get("/", lambda r: web.Response(text=page, content_type="text/html"))
    app.router.add_get("/assets/app.js", lambda r: web.Response(text="js();",
                                                                content_type="text/javascript"))

    async def echo_post(request):
        return web.Response(text=f"got {len(await request.read())}")
    app.router.add_post("/api/upload", echo_post)

    async def ws(request):
        w = web.WebSocketResponse(); await w.prepare(request)
        await w.send_bytes(b"\x04\x11frame")
        async for _ in w:
            pass
        return w
    app.router.add_get("/api/websockets", ws)
    return app


@pytest.mark.asyncio
async def test_single_upstream_index_assets_api_and_ws(tmp_path):
    from aiohttp.test_utils import TestClient, TestServer
    up = TestClient(TestServer(await _upstream_app())); await up.start_server()
    app = gateway.create_app("styx", "pw", upstream_port=up.server.port,
                             cursor_workaround=True)
    c = TestClient(TestServer(app)); await c.start_server()
    h = {"Authorization": _basic("styx", "pw")}
    try:
        html = await (await c.get("/", headers=h)).text()
        assert "cursor:none" in html                       # cursor workaround injected
        assert (await (await c.get("/assets/app.js", headers=h)).text()) == "js();"
        r = await c.post("/api/upload", data=b"12345", headers=h)
        assert (await r.text()) == "got 5"
        for path in ("/api/websockets", "/websockets", "/websocket"):
            ws = await c.ws_connect(path, headers=h)
            msg = await ws.receive()
            assert msg.data == b"\x04\x11frame"
            await ws.close()
        assert (await c.get("/assets/app.js")).status == 401  # auth on proxied paths
    finally:
        await c.close(); await up.close()


@pytest.mark.asyncio
async def test_ws_proxy_upstream_down_returns_502():
    from aiohttp.test_utils import TestClient, TestServer
    app = gateway.create_app("styx", "pw", upstream_port=1)   # nothing listens on :1
    c = TestClient(TestServer(app)); await c.start_server()
    try:
        r = await c.get("/api/websockets", headers={"Authorization": _basic("styx", "pw"),
                                                    "Upgrade": "websocket",
                                                    "Connection": "Upgrade",
                                                    "Sec-WebSocket-Version": "13",
                                                    "Sec-WebSocket-Key": "dGhlIHNhbXBsZSBub25jZQ=="})
        assert r.status == 502
        assert (await c.get("/", headers={"Authorization": _basic("styx", "pw")})).status == 502
    finally:
        await c.close()


def test_inject_cursor_hide():
    html = "<html><head></head><body></body></html>"
    assert gateway.inject_cursor_hide(html, False) == html
    out = gateway.inject_cursor_hide(html, True)
    assert "cursor:none !important" in out and out.index("cursor:none") < out.index("</head>")
```

In `agent/tests/test_styx_agent.py`, add:

```python
def test_gateway_cmd_has_no_web_dir_and_passes_cursor_flag(tmp_path):
    cfg = {"install_dir": str(tmp_path), "port": 8443, "selkies_user": "u",
           "selkies_password": "p", "stream_settings": {"cursor_workaround": True}}
    cmd, env = styx_agent.build_gateway_cmd(cfg, 1234)
    assert cmd[-2:] == ["8443", "1234"]
    assert not any(a.endswith("/web") for a in cmd)
    assert env["STYX_GW_CURSOR_WORKAROUND"] == "1"
```

- [ ] **Step 3: Run to verify failure**

Run: `cd agent && ../backend/.venv/bin/python -m pytest tests/test_gateway.py tests/test_gateway_idle.py tests/test_styx_agent.py -q`
Expected: FAIL (signature mismatch, missing `inject_cursor_hide`).

- [ ] **Step 4: Implement**

Add near the other injectors in `agent/gateway.py`:

```python
CURSOR_HIDE_CSS = ("<style id=\"styx-cursor\">video,canvas,#videoContainer,"
                   "#overlayInput{cursor:none !important}</style>")


def inject_cursor_hide(html: str, enabled: bool) -> str:
    """GNOME portal capture bakes the cursor into the video and sends no cursor
    metadata, so the browser cursor doubles it (flicker, stale cursor on leave).
    Hide the browser one; the in-video cursor is the only cursor (spec §5.2)."""
    if not enabled or "</head>" not in html:
        return html
    return html.replace("</head>", CURSOR_HIDE_CSS + "</head>", 1)
```

Change `create_app` signature to the one in **Interfaces** and replace the `ws_proxy` upstream URL, `index`, and router block:

```python
    UPSTREAM = f"http://127.0.0.1:{upstream_port}"
    HOP = {"host", "connection", "keep-alive", "transfer-encoding", "upgrade",
           "authorization", "origin", "content-length", "accept-encoding"}

    async def ws_proxy(request):
        # 2.0 serves the stream at /api/websockets; legacy client paths map to it.
        async with aiohttp.ClientSession() as session:
            try:
                ws_client = await session.ws_connect(
                    f"ws://127.0.0.1:{upstream_port}/api/websockets", max_msg_size=0)
            except aiohttp.ClientError:
                return web.Response(status=502, text="stream backend unavailable")
            # KEEP the existing ws_proxy body verbatim from here: the lines
            # `conns["n"] += 1` through `return ws_server` (gateway.py:238-293).

    async def index(_request):
        try:
            async with aiohttp.ClientSession() as s, s.get(UPSTREAM + "/") as r:
                html = await r.text()
        except aiohttp.ClientError:
            return web.Response(status=502, text="stream backend unavailable")
        html = inject_title(html, socket.gethostname())
        html = inject_idle_watchdog(html, idle_timeout_s, idle_lead_s, idle_enabled)
        html = inject_cursor_hide(html, cursor_workaround)
        return web.Response(text=html, content_type="text/html")

    async def http_proxy(request):
        """Everything else (client assets, /api/* REST) goes to selkies as-is."""
        headers = {k: v for k, v in request.headers.items() if k.lower() not in HOP}
        body = await request.read() if request.body_exists else None
        try:
            async with aiohttp.ClientSession(auto_decompress=False) as s, s.request(
                    request.method, UPSTREAM + request.rel_url.path_qs,
                    headers=headers, data=body, allow_redirects=False) as r:
                payload = await r.read()
                out = {k: v for k, v in r.headers.items() if k.lower() not in HOP}
                return web.Response(status=r.status, body=payload, headers=out)
        except aiohttp.ClientError:
            return web.Response(status=502, text="stream backend unavailable")

    _write_state()
    app = web.Application(middlewares=[auth_mw], client_max_size=0)
    for path in ("/api/websockets", "/websockets", "/websocket"):
        app.router.add_get(path, ws_proxy)
    app.router.add_get("/", index)
    if files_dir and os.path.isdir(files_dir):
        app.router.add_get("/files", files)
        app.router.add_get("/files/{path:.*}", files)
    app.router.add_route("*", "/{tail:.*}", http_proxy)
    return app
```

Keep `"content-encoding"` passthrough: `auto_decompress=False` + forwarding `Content-Encoding` keeps compressed assets intact. Remove `"accept-encoding"` from `HOP` if a test shows garbled assets; it is in HOP to make the upstream send identity bodies.

`main()` becomes:

```python
def main() -> None:
    listen_port, upstream_port = int(sys.argv[1]), int(sys.argv[2])
    user = os.environ["STYX_GW_USER"]
    password = os.environ["STYX_GW_PASSWORD"]
    files_dir = os.path.expanduser(os.environ.get("STYX_FILES_DIR", "~/Downloads"))
    state_file = os.environ.get("STYX_GW_STATE", "")
    idle_timeout_s = int(os.environ.get("STYX_GW_IDLE_TIMEOUT_S", "0") or "0")
    idle_lead_s = int(os.environ.get("STYX_GW_IDLE_WARN_S", "60") or "60")
    idle_enabled = os.environ.get("STYX_GW_IDLE_ENABLED", "") == "1"
    cursor = os.environ.get("STYX_GW_CURSOR_WORKAROUND", "") == "1"
    web.run_app(create_app(user, password, upstream_port, files_dir,
                           state_file=state_file, idle_timeout_s=idle_timeout_s,
                           idle_lead_s=idle_lead_s, idle_enabled=idle_enabled,
                           cursor_workaround=cursor),
                host="0.0.0.0", port=listen_port)
```

`build_gateway_cmd` in `agent/styx_agent.py`:

```python
    env["STYX_GW_CURSOR_WORKAROUND"] = "1" if ss.get("cursor_workaround") else ""
    cmd = [str(install / "venv/bin/python"), str(install / "gateway.py"),
           str(cfg["port"]), str(upstream_port)]
```

Also update the module docstring line 4 ("Mirrors the upstream container's nginx layout…") to: "Fronts selkies 2.0 (which serves its own client and /api/*) with auth, idle enforcement and injected shims."

- [ ] **Step 5: Run tests**

Run: `cd agent && ../backend/.venv/bin/python -m pytest tests -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add agent/gateway.py agent/styx_agent.py agent/tests/
git commit -m "feat(agent): gateway proxies selkies 2.0 single upstream; cursor workaround"
```

---

### Task 6: Refactor — move helpers out of `styx_agent.py` (no behavior change)

Makes room for Task 7 within the 500-line rule.

**Files:**
- Create: `agent/health.py` — move `gw_state_path`, `active_connections`, `idle_seconds`, `stream_starving_seconds` verbatim from `agent/styx_agent.py:75-150`.
- Create: `agent/seat_labwc.py` — move `start_shell` and `start_clipboard_bridge` closures out of `run()` as module functions:
  - `start_shell(install_dir: Path, seat_socket: str, runtime_dir: str, log) -> subprocess.Popen | None`
  - `start_clipboard_bridge(install_dir: Path, seat_socket: str | None, app_socket: str | None, runtime_dir: str, log_dir: Path) -> subprocess.Popen | None`
- Delete from `agent/styx_agent.py`: `read_encoder_progress`, `stream_frozen`, `FREEZE_TIMEOUT_S`, and the "Frozen-engine watchdog" block in `run()` (lines ≈471-494). It is dead on 2.0 (no `EncFPS:` line; the gateway frame watchdog covers stalls since 0.4.10).
- Modify: `agent/styx_agent.py` — `from health import gw_state_path, active_connections, idle_seconds, stream_starving_seconds`; call `seat_labwc.start_shell(...)` / `seat_labwc.start_clipboard_bridge(...)`.
- Test: move the matching tests from `agent/tests/test_styx_agent.py` to `agent/tests/test_health.py` (change `styx_agent.` → `health.`); delete tests for `read_encoder_progress` / `stream_frozen`.

- [ ] **Step 1: Move code and tests exactly as listed (no logic edits).**
- [ ] **Step 2: Run tests** — `cd agent && ../backend/.venv/bin/python -m pytest tests -q` → PASS; `wc -l agent/styx_agent.py` → below 560.
- [ ] **Step 3: Commit**

```bash
git add agent/
git commit -m "refactor(agent): split health + labwc seat helpers out of styx_agent"
```

---

### Task 7: Supervisor — GNOME seat wiring, escalation, consent state, 0.5.0

**Files:**
- Modify: `agent/styx_agent.py` (`run`, `_restart_engine`, `health_payload`, `SETTINGS_CHANGE_RESTART`, `AGENT_VERSION`)
- Test: `agent/tests/test_styx_agent.py`

**Interfaces:**
- Consumes: `seat_gnome.GnomeSeat`, `seat_gnome.gnome_available`, `engine.build_selkies_cmd(cfg, port, seat)`.
- Produces: `pick_seat_shell(cfg: dict) -> str` (`"gnome"` | `"labwc"` | `"mirror"`).
- Produces: `class Escalation(limit: int = 3, window_s: float = 600)` with `record(now: float) -> bool` (True when the restart that was just recorded hits the limit inside the window; then resets).
- Produces: `needs_consent(starving_s: float | None, token_path: Path) -> bool`.
- Produces: `settings_restart_keys(old: dict, new: dict) -> tuple[str, ...]` — which procs to restart on a settings change.
- `health_payload` adds keys: `seat_shell`, `seat_restarts`, `degraded`, `needs_consent`.

- [ ] **Step 1: Write the failing tests**

```python
from pathlib import Path


def test_pick_seat_shell(monkeypatch):
    monkeypatch.setattr(styx_agent.seat_gnome, "gnome_available", lambda: (True, ""))
    assert styx_agent.pick_seat_shell({"mode": "mirror"}) == "mirror"
    assert styx_agent.pick_seat_shell({"mode": "seat", "stream_settings": {}}) == "gnome"
    assert styx_agent.pick_seat_shell(
        {"mode": "seat", "stream_settings": {"seat_shell": "labwc"}}) == "labwc"
    monkeypatch.setattr(styx_agent.seat_gnome, "gnome_available", lambda: (False, "x"))
    assert styx_agent.pick_seat_shell({"mode": "seat", "stream_settings": {}}) == "labwc"


def test_escalation_three_in_window():
    e = styx_agent.Escalation(limit=3, window_s=600)
    assert not e.record(0) and not e.record(100)
    assert e.record(200)              # third inside 10 min -> escalate
    assert not e.record(300)          # reset after escalating
    e2 = styx_agent.Escalation(limit=3, window_s=600)
    assert not e2.record(0) and not e2.record(400) and not e2.record(1100)


def test_needs_consent(tmp_path):
    tok = tmp_path / "portal-restore-token"
    assert styx_agent.needs_consent(25.0, tok) is True
    assert styx_agent.needs_consent(5.0, tok) is False
    assert styx_agent.needs_consent(None, tok) is False
    tok.write_text("t")
    assert styx_agent.needs_consent(25.0, tok) is False


def test_settings_change_keeps_gnome_seat():
    old = {"video_crf": 25, "seat_width": 2560, "seat_height": 1440}
    keys = styx_agent.settings_restart_keys(old, {**old, "video_crf": 30})
    assert "seat" not in keys and "selkies" in keys and "gateway" in keys
    keys = styx_agent.settings_restart_keys(old, {**old, "seat_width": 1920})
    assert "seat" in keys


def test_run_config_from_0411_is_accepted(tmp_path, monkeypatch):
    cfg = {"server": "https://x", "agent_token": "t", "workstation_id": "w",
           "port": 8443, "selkies_user": "u", "selkies_password": "p",
           "mode": "seat", "display": "", "seat_socket_index": 2,
           "stream_settings": {"framerate": 60, "h264_crf": 23},
           "install_dir": str(tmp_path), "ca_pin": "", "server_cert": ""}
    monkeypatch.setattr(styx_agent.seat_gnome, "gnome_available", lambda: (True, ""))
    assert styx_agent.pick_seat_shell(cfg) == "gnome"
    p = styx_agent.health_payload(cfg, True, True)
    assert p["agent_version"] == "0.5.0" and p["needs_consent"] is False
```

Update the two version-pin assertions in `agent/tests/test_styx_agent.py` (`== "0.4.11"`) to `"0.5.0"`.

- [ ] **Step 2: Run to verify failure**

Run: `cd agent && ../backend/.venv/bin/python -m pytest tests/test_styx_agent.py -q`
Expected: FAIL (missing names).

- [ ] **Step 3: Implement the helpers**

```python
import seat_gnome

AGENT_VERSION = "0.5.0"
CONSENT_PENDING_S = 20
TOKEN_PATH = HOME / ".local/state/pixelflux/portal-restore-token"
SEAT_KEYS = ("seat_shell", "seat_width", "seat_height")


def pick_seat_shell(cfg: dict) -> str:
    if cfg.get("mode") != "seat":
        return "mirror"
    want = (cfg.get("stream_settings") or {}).get("seat_shell", "gnome")
    if want == "gnome":
        ok, why = seat_gnome.gnome_available()
        if ok:
            return "gnome"
        print(f"GNOME seat unavailable ({why}); using labwc seat", flush=True)
    return "labwc"


class Escalation:
    """N engine restarts inside a window -> restart the whole seat (spec §5.4)."""
    def __init__(self, limit: int = 3, window_s: float = 600):
        self.limit, self.window_s, self.times = limit, window_s, []

    def record(self, now: float) -> bool:
        self.times = [t for t in self.times if now - t < self.window_s] + [now]
        if len(self.times) >= self.limit:
            self.times = []
            return True
        return False


def needs_consent(starving_s: float | None, token_path: Path = TOKEN_PATH) -> bool:
    return (starving_s is not None and starving_s >= CONSENT_PENDING_S
            and not token_path.exists())


def settings_restart_keys(old: dict, new: dict) -> tuple[str, ...]:
    keys = ("selkies", "shell", "clipboard", "gateway")
    if any(old.get(k) != new.get(k) for k in SEAT_KEYS):
        keys += ("seat",)
    return keys
```

`health_payload` gains parameters with defaults so existing callers keep working:

```python
def health_payload(cfg: dict, selkies_alive: bool, gateway_alive: bool,
                   seat_shell: str = "", seat_restarts: int = 0,
                   degraded: bool = False) -> dict:
    starving = stream_starving_seconds(cfg, gateway_alive)
    return {
        ...existing keys...,
        "seat_shell": seat_shell or cfg.get("mode", "mirror"),
        "seat_restarts": seat_restarts,
        "degraded": degraded,
        "needs_consent": seat_shell == "gnome" and needs_consent(starving),
    }
```

- [ ] **Step 4: Wire `run()`**

Inside `run()`, after the log files are opened:

```python
    shell_kind = pick_seat_shell(cfg)
    gseat = (seat_gnome.GnomeSeat(INSTALL_DIR, runtime_dir, seat_log)
             if shell_kind == "gnome" else None)
    escalation, degraded = Escalation(), False

    def ensure_gnome_seat() -> bool:
        if gseat.alive():
            return True
        ss = cfg.get("stream_settings") or {}
        engine.ensure_seat_sink()
        gseat.start(int(ss.get("seat_width") or 2560), int(ss.get("seat_height") or 1440))
        if not gseat.ready():
            nonlocal last_error
            last_error = "GNOME seat failed to start — see logs/seat.log"
            gseat.stop()
            return False
        return True
```

- Only take the `wayland0_guard`, `start_shell` and clipboard branches when `shell_kind == "labwc"` (replace `seat_mode` checks with `shell_kind == "labwc"` in those blocks).
- In `start_selkies()`: if `gseat` and not `ensure_gnome_seat()` → `return None`; build with `engine.build_selkies_cmd(cfg, internal_port, gseat.info() if gseat else None)`; drop `control_port` everywhere; skip the socket-wait/`seat_socket_index` logic for gnome.
- Supervisor loop, before the selkies check: `if gseat and not gseat.alive(): _terminate(procs["selkies"]); procs["selkies"] = None` (selkies is restarted against the new seat by the next branch).
- Stream-start watchdog branch becomes:

```python
        if selkies_ok and starving is not None and starving >= FRAME_START_TIMEOUT_S \
                and not (gseat and needs_consent(starving)):
            print(f"watchdog: viewer frameless {int(starving)}s — restarting selkies",
                  flush=True)
            if gseat:
                _terminate(procs["selkies"]); procs["selkies"] = None
                if escalation.record(time.time()):
                    print("watchdog: 3 restarts in 10 min — restarting GNOME seat",
                          flush=True)
                    gseat.stop(); degraded = True
            else:
                _restart_engine(procs)
            continue
```

(While consent is pending, restarting selkies only re-opens the dialog; report `needs_consent` instead.)
- Surface it in the portal through the existing `last_error` field (already shown in the workstation list), right after computing `starving`:

```python
        if gseat and needs_consent(starving):
            last_error = CONSENT_ERROR
        elif last_error == CONSENT_ERROR:
            last_error = None
```

with module constant
`CONSENT_ERROR = ("GNOME seat needs one-time screen-share consent: run "
"'styx-agent doctor --grant' on the box")` and test
`def test_consent_error_names_the_fix(): assert "doctor --grant" in styx_agent.CONSENT_ERROR`.
- Heartbeat call: `health_payload(cfg, selkies_ok, gateway_ok, shell_kind, gseat.restarts if gseat else 0, degraded)`.
- Settings change block: replace `for key in SETTINGS_CHANGE_RESTART:` with `keys = settings_restart_keys(old_ss, hb["stream_settings"])` (capture `old_ss = cfg["stream_settings"]` before assigning), terminate those procs, and `if "seat" in keys and gseat: gseat.stop()`.
- Shutdown: after terminating procs, `if gseat: gseat.stop()`.
- Delete `SETTINGS_CHANGE_RESTART` constant (replaced by `settings_restart_keys`).

- [ ] **Step 5: Run tests + line count**

Run: `cd agent && ../backend/.venv/bin/python -m pytest tests -q && wc -l styx_agent.py engine.py`
Expected: PASS; both files < 500. If `engine.py` ≥ 500, move the labwc-only builders (`build_waybar_config`, `build_waybar_dock`, `build_labwc_rc`, `build_labwc_environment`, `build_autostart`, `write_seat_config`, wallpaper helpers) into `agent/seat_labwc.py` and re-export nothing — update imports in `seat_labwc.start_shell` and the tests (`engine.` → `seat_labwc.`).

- [ ] **Step 6: Commit**

```bash
git add agent/
git commit -m "feat(agent): supervise headless GNOME seat; escalation + consent state; 0.5.0"
```

---

### Task 8: `styx-agent doctor --grant` consent flow

**Files:**
- Create: `agent/grant.py`
- Modify: `agent/styx_agent.py` (`main` argument parsing: `doctor --grant [--local]`)
- Test: `agent/tests/test_grant.py`

**Interfaces:**
- Produces: `grant(cfg: dict, local: bool = False, timeout_s: float = 90) -> int` (exit code: 0 granted, 1 failed).
- Produces: `rd_key_cmds(bus: str, keysym: int) -> list[list[str]]` — the gdbus calls that press+release one key through `org.gnome.Mutter.RemoteDesktop` (session path substituted at runtime).
- Consumes: `TOKEN_PATH`, `seat_gnome.GnomeSeat`, running selkies via the gateway port.

Behavior (`CONSENT=auto` from Task 1): trigger a stream (WS connect to the local gateway with basic auth from config, send `SETTINGS,{...}` + `START_VIDEO`), wait 3 s, press Return via Mutter RemoteDesktop on the seat bus, poll for `TOKEN_PATH` up to `timeout_s`. `--local` (or `CONSENT=local`): for one request, set the seat bus activation env `DISPLAY` to the physical display (`cfg["display"]` or `:0`), kill the portal backend on the seat bus so it re-activates with that env, trigger the stream, print "Click Allow on the box's screen", poll for the token, then restore `DISPLAY=` and kill the backend again.

- [ ] **Step 1: Write the failing tests**

```python
# agent/tests/test_grant.py
import grant


def test_rd_key_cmds_press_and_release():
    cmds = grant.rd_key_cmds("unix:path=/b", 0xff0d)
    joined = [" ".join(c) for c in cmds]
    assert any("NotifyKeyboardKeysym" in j and "65293 true" in j for j in joined)
    assert any("NotifyKeyboardKeysym" in j and "65293 false" in j for j in joined)


def test_grant_returns_0_when_token_appears(tmp_path, monkeypatch):
    tok = tmp_path / "tok"
    monkeypatch.setattr(grant, "TOKEN_PATH", tok)
    monkeypatch.setattr(grant, "_trigger_stream", lambda cfg: tok.write_text("x"))
    monkeypatch.setattr(grant, "_press_return", lambda bus: None)
    monkeypatch.setattr(grant, "_seat_bus", lambda: "unix:path=/b")
    assert grant.grant({"port": 8443}, timeout_s=1) == 0


def test_grant_times_out(tmp_path, monkeypatch):
    monkeypatch.setattr(grant, "TOKEN_PATH", tmp_path / "never")
    monkeypatch.setattr(grant, "_trigger_stream", lambda cfg: None)
    monkeypatch.setattr(grant, "_press_return", lambda bus: None)
    monkeypatch.setattr(grant, "_seat_bus", lambda: "unix:path=/b")
    assert grant.grant({"port": 8443}, timeout_s=0.3) == 1


def test_grant_local_without_display_errors(tmp_path, monkeypatch):
    monkeypatch.setattr(grant, "TOKEN_PATH", tmp_path / "never")
    monkeypatch.setattr(grant, "_seat_bus", lambda: "unix:path=/b")
    monkeypatch.setattr(grant, "_x_display_alive", lambda d: False)
    assert grant.grant({"port": 8443, "display": ""}, local=True, timeout_s=0.3) == 1
```

- [ ] **Step 2: Run to verify failure** — `cd agent && ../backend/.venv/bin/python -m pytest tests/test_grant.py -q` → FAIL (no module).

- [ ] **Step 3: Implement**

```python
# agent/grant.py
"""One-time portal consent for the GNOME seat (spec §5.5). Success = pixelflux
wrote its restore token; later sessions start without a prompt."""
import asyncio
import json
import os
import re
import subprocess
import time
from pathlib import Path

TOKEN_PATH = Path.home() / ".local/state/pixelflux/portal-restore-token"
INSTALL_DIR = Path.home() / ".local/share/styx-agent"
_RD = ("org.gnome.Mutter.RemoteDesktop", "/org/gnome/Mutter/RemoteDesktop")


def _seat_bus() -> str:
    return (INSTALL_DIR / "gnome-bus.addr").read_text().strip()


def _gdbus(bus: str, *args: str) -> str:
    return subprocess.run(["gdbus", "call", "--session", *args],
                          env={**os.environ, "DBUS_SESSION_BUS_ADDRESS": bus},
                          capture_output=True, text=True, timeout=10).stdout


def rd_key_cmds(bus: str, keysym: int, session: str = "{session}") -> list[list[str]]:
    m = "org.gnome.Mutter.RemoteDesktop.Session"
    return [["gdbus", "call", "--session", "-d", _RD[0], "-o", session, "-m",
             f"{m}.NotifyKeyboardKeysym", str(keysym), state]
            for state in ("true", "false")]


def _press_return(bus: str) -> None:
    out = _gdbus(bus, "-d", _RD[0], "-o", _RD[1], "-m",
                 "org.gnome.Mutter.RemoteDesktop.CreateSession")
    session = re.search(r"'(/[^']+)'", out).group(1)
    _gdbus(bus, "-d", _RD[0], "-o", session, "-m",
           "org.gnome.Mutter.RemoteDesktop.Session.Start")
    for cmd in rd_key_cmds(bus, 0xff0d, session):
        subprocess.run(cmd, env={**os.environ, "DBUS_SESSION_BUS_ADDRESS": bus},
                       capture_output=True, timeout=10)
    _gdbus(bus, "-d", _RD[0], "-o", session, "-m",
           "org.gnome.Mutter.RemoteDesktop.Session.Stop")


def _trigger_stream(cfg: dict) -> None:
    """Open a viewer on the local gateway so selkies starts its portal session."""
    import aiohttp

    async def go():
        auth = aiohttp.BasicAuth(cfg["selkies_user"], cfg["selkies_password"])
        async with aiohttp.ClientSession(auth=auth) as s, s.ws_connect(
                f"http://127.0.0.1:{cfg['port']}/api/websockets") as ws:
            await ws.send_str("SETTINGS," + json.dumps(
                {"displayId": "primary", "initialClientWidth": 1920,
                 "initialClientHeight": 1080}))
            await ws.send_str("START_VIDEO")
            await asyncio.sleep(8)
    asyncio.run(go())


def _x_display_alive(display: str) -> bool:
    return bool(display) and subprocess.run(
        ["xset", "-display", display, "q"], capture_output=True).returncode == 0


def _wait_token(timeout_s: float) -> bool:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if TOKEN_PATH.exists():
            return True
        time.sleep(0.2)
    return False


def grant(cfg: dict, local: bool = False, timeout_s: float = 90) -> int:
    bus = _seat_bus()
    if local:
        display = cfg.get("display") or ":0"
        if not _x_display_alive(display):
            print(f"--local needs a logged-in desktop on {display}; none found.")
            return 1
        subprocess.run(["dbus-update-activation-environment", f"DISPLAY={display}"],
                       env={**os.environ, "DBUS_SESSION_BUS_ADDRESS": bus})
        subprocess.run(["pkill", "-f", "xdg-desktop-portal-gnome"], capture_output=True)
        print("Click 'Allow' in the screen-share dialog on this box's screen.")
    try:
        import threading
        threading.Thread(target=_trigger_stream, args=(cfg,), daemon=True).start()
        if not local:
            time.sleep(3)
            _press_return(bus)
        ok = _wait_token(timeout_s)
    finally:
        if local:
            subprocess.run(["dbus-update-activation-environment", "DISPLAY="],
                           env={**os.environ, "DBUS_SESSION_BUS_ADDRESS": bus})
            subprocess.run(["pkill", "-f", "xdg-desktop-portal-gnome"], capture_output=True)
    print("Consent granted." if ok else "No consent recorded; retry with --local.")
    return 0 if ok else 1
```

Note on `pkill -f xdg-desktop-portal-gnome`: it would also kill the physical session's portal backend; it is re-activated on demand by D-Bus, which is acceptable for a one-time admin step. Print this in the `--local` message.

In `test_grant_returns_0_when_token_appears` the thread runs the monkeypatched `_trigger_stream`, which writes the token.

`styx_agent.main`: when argv is `doctor --grant` call `grant.grant(cfg, local="--local" in sys.argv)` and return its code.

- [ ] **Step 4: Run tests** — `cd agent && ../backend/.venv/bin/python -m pytest tests -q` → PASS.
- [ ] **Step 5: Commit**

```bash
git add agent/grant.py agent/styx_agent.py agent/tests/test_grant.py
git commit -m "feat(agent): doctor --grant one-time portal consent for GNOME seat"
```

---

### Task 9: Seat resolution (fixed, plus live resize only if Task 1 says `RESIZE=live`)

**Fixed resolution is already delivered** by Tasks 2/4/7 (`seat_width`/`seat_height` → `--virtual-monitor`; changing them restarts the seat). This task adds live resize **only when** Task 1 recorded `RESIZE=live`; otherwise mark this task skipped in the plan and move on.

**Files (RESIZE=live only):**
- Modify: `agent/seat_gnome.py` — add `apply_mode(bus: str, width: int, height: int) -> bool`
- Modify: `agent/gateway.py` — on client text message `r,<W>x<H>` (selkies resize), write `{"resize": [W, H]}` into the state file
- Modify: `agent/styx_agent.py` — in the loop, if gw state has a new `resize` and `gseat`, call `apply_mode`
- Test: `agent/tests/test_seat_gnome.py`, `agent/tests/test_gateway.py`

- [ ] **Step 1: Failing tests**

```python
def test_apply_mode_picks_matching_mode(monkeypatch):
    state = ("(uint32 7, [(('Meta-0', 'MetaVendor', 'Virtual', '0x00'), "
             "[('1920x1080@60.000', 1920, 1080, 60.0, 1.0, [1.0], {}), "
             "('2560x1440@60.000', 2560, 1440, 60.0, 1.0, [1.0], {})], {})], [], {})")
    calls = []
    monkeypatch.setattr(seat_gnome, "_gdbus_display", lambda bus, *a: calls.append(a) or state)
    assert seat_gnome.apply_mode("b", 2560, 1440) is True
    applied = " ".join(calls[-1])
    assert "2560x1440@60.000" in applied and "'Meta-0'" in applied and "uint32 7" in applied
    assert seat_gnome.apply_mode("b", 1234, 567) is False
```

```python
@pytest.mark.asyncio
async def test_resize_message_recorded_in_state(tmp_path):
    import asyncio, json
    from aiohttp.test_utils import TestClient, TestServer
    up = TestClient(TestServer(await _upstream_app())); await up.start_server()
    state = tmp_path / "gw_state.json"
    app = gateway.create_app("styx", "pw", upstream_port=up.server.port,
                             state_file=str(state))
    c = TestClient(TestServer(app)); await c.start_server()
    try:
        ws = await c.ws_connect("/api/websockets",
                                headers={"Authorization": _basic("styx", "pw")})
        await ws.send_str("r,1920x1080")
        await asyncio.sleep(0.1)
        assert json.loads(state.read_text())["resize"] == [1920, 1080]
        await ws.close()
    finally:
        await c.close(); await up.close()
```

- [ ] **Step 2: Implement**

```python
def _gdbus_display(bus: str, *args: str) -> str:
    return subprocess.run(
        ["gdbus", "call", "--session", "-d", "org.gnome.Mutter.DisplayConfig",
         "-o", "/org/gnome/Mutter/DisplayConfig", "-m", *args],
        env={**os.environ, "DBUS_SESSION_BUS_ADDRESS": bus},
        capture_output=True, text=True, timeout=10).stdout


def apply_mode(bus: str, width: int, height: int) -> bool:
    state = _gdbus_display(bus, "org.gnome.Mutter.DisplayConfig.GetCurrentState")
    serial = re.search(r"uint32 (\d+)", state)
    conn = re.search(r"\(\('([^']+)'", state)
    mode = re.search(rf"'({width}x{height}@[0-9.]+)'", state)
    if not (serial and conn and mode):
        return False
    _gdbus_display(bus, "org.gnome.Mutter.DisplayConfig.ApplyMonitorsConfig",
                   f"uint32 {serial.group(1)}", "1",
                   f"[(0, 0, 1.0, uint32 0, true, [('{conn.group(1)}', "
                   f"'{mode.group(1)}', @a{{sv}} {{}})])]", "@a{sv} {}")
    return True
```

Gateway `mark_input`: before `is_activity` early return, add

```python
        if isinstance(data, str) and data.startswith("r,"):
            m = re.match(r"r,(\d+)x(\d+)", data)
            if m:
                stream["resize"] = [int(m.group(1)), int(m.group(2))]
                _write_state()
```

and include `"resize": stream.get("resize")` in `_write_state`'s JSON. Supervisor: track `last_resize`; when gw state `resize` differs and `gseat`, call `seat_gnome.apply_mode(gseat.bus, *resize)`.

- [ ] **Step 3: Run tests, commit**

```bash
git add agent/
git commit -m "feat(agent): follow browser size on the GNOME seat via Mutter DisplayConfig"
```

---

### Task 10: Packaging — artifacts, enroll `--upgrade`, rollback, backend file lists

**Files:**
- Modify: `scripts/build_agent_artifacts.sh:12-17,37-53,54-81,107-118`
- Modify: `agent/enroll.sh:216-265` (+ argument parsing for `--upgrade`)
- Delete: `agent/selkies_launcher.py`
- Modify: `backend/app/services/artifacts.py:20-29`, `backend/app/routers/enroll.py:65-72`, `backend/app/services/workstations.py:137-143`
- Modify: `agent/styx_agent.py` (`rollback` subcommand)
- Test: `backend/tests/test_artifacts.py`, `backend/tests/test_workstation_enroll.py`, `agent/tests/test_styx_agent.py`

**Interfaces:**
- Agent files served: `agent.py, engine.py, gateway.py, seat_gnome.py, seat_labwc.py, health.py, grant.py, clipboard_bridge.py, uninstall` (labwc fallback still uses the bridge until Phase 2).
- Artifacts: `wheelhouse-x86_64.tar.gz`, `nwg-shell-x86_64.tar.gz` (labwc fallback). Removed: `selkies-web.tar.gz`, `libshim-x86_64.tar.gz`.
- `rollback(install_dir: Path) -> int`: swaps `install_dir` with `install_dir.with_name(install_dir.name + ".prev")` and restarts the user service.

- [ ] **Step 1: Failing backend tests**

```python
# backend/tests/test_workstation_enroll.py (append)
from app.services.workstations import AGENT_UPDATE_FILES


def test_agent_files_for_0_5():
    names = {local for _, local in AGENT_UPDATE_FILES}
    assert {"seat_gnome.py", "seat_labwc.py", "health.py", "grant.py"} <= names
    assert "selkies_launcher.py" not in names


@pytest.mark.asyncio
async def test_new_agent_files_are_served(client):
    for f in ("seat_gnome.py", "seat_labwc.py", "health.py", "grant.py"):
        assert (await client.get(f"/api/enroll/{f}")).status_code == 200
    assert (await client.get("/api/enroll/selkies_launcher.py")).status_code == 404
```

```python
# backend/tests/test_artifacts.py (append)
from app.services.artifacts import ARTIFACTS


def test_artifacts_for_selkies2():
    assert "selkies-web.tar.gz" not in ARTIFACTS and "libshim-x86_64.tar.gz" not in ARTIFACTS
    assert "wheelhouse-x86_64.tar.gz" in ARTIFACTS
```

Agent test:

```python
def test_rollback_swaps_dirs(tmp_path, monkeypatch):
    cur, prev = tmp_path / "styx-agent", tmp_path / "styx-agent.prev"
    cur.mkdir(); prev.mkdir(); (cur / "v").write_text("new"); (prev / "v").write_text("old")
    monkeypatch.setattr(styx_agent.subprocess, "run", lambda *a, **k: None)
    assert styx_agent.rollback(cur) == 0
    assert (cur / "v").read_text() == "old" and (prev / "v").read_text() == "new"
    assert styx_agent.rollback(tmp_path / "missing") == 1
```

- [ ] **Step 2: Run to verify failure** — backend + agent suites → FAIL on the new tests.

- [ ] **Step 3: Implement**

`backend/app/services/workstations.py`:

```python
AGENT_UPDATE_FILES = [
    ("agent.py", "styx_agent.py"),
    ("engine.py", "engine.py"),
    ("gateway.py", "gateway.py"),
    ("seat_gnome.py", "seat_gnome.py"),
    ("seat_labwc.py", "seat_labwc.py"),
    ("health.py", "health.py"),
    ("grant.py", "grant.py"),
    ("clipboard_bridge.py", "clipboard_bridge.py"),
]
```

`backend/app/routers/enroll.py`: delete the `selkies_launcher.py` route; add:

```python
@router.get("/seat_gnome.py")
async def seat_gnome_py():
    return _serve("seat_gnome.py")


@router.get("/seat_labwc.py")
async def seat_labwc_py():
    return _serve("seat_labwc.py")


@router.get("/health.py")
async def health_py():
    return _serve("health.py")


@router.get("/grant.py")
async def grant_py():
    return _serve("grant.py")
```

`backend/app/services/artifacts.py`: remove the `selkies-web.tar.gz` and `libshim-x86_64.tar.gz` entries; fix the line-7 comment to "Prebuilt agent artifacts (wheelhouse, nwg-shell) served to enrolling workstations."

`scripts/build_agent_artifacts.sh`:
- delete `SELKIES_COMMIT`, `SELKIES_URL`, `SELKIES_BASEIMAGE`, the `[2/4] selkies-web` block, the `[3/4] libshim` block and the `DEB_SHA256`/`UBU` variables they use;
- wheel line becomes `"$PIP" -q wheel --wheel-dir /out/wheelhouse selkies==2.0.0 pixelflux==2.1.0 pcmflux==2.1.0 setuptools=="$SETUPTOOLS_VER" aiohttp=="$AIOHTTP_VER" pulsectl=="$PULSECTL_VER"` (keep `xkbcommon==0.5` only if `pip download selkies==2.0.0` shows it as a dependency; otherwise drop it and the `yum install` line);
- set `AIOHTTP_VER="3.14.1"` (selkies 2.0 requires `>=3.14.1`);
- renumber steps `[1/2] wheelhouse`, `[2/2] nwg-shell`; update the final `ls`/loop lists.

`agent/enroll.sh`:
- parse `--upgrade` (sets `UPGRADE=1`; skips token requirement, preflight port check and registration step 8; reuses existing `config.json`);
- before step 7 when `UPGRADE=1`: `systemctl --user stop styx-agent || true; rm -rf "$INSTALL_DIR.prev"; cp -a "$INSTALL_DIR" "$INSTALL_DIR.prev"`;
- file list: `"agent.py styx_agent.py" "engine.py engine.py" "gateway.py gateway.py" "seat_gnome.py seat_gnome.py" "seat_labwc.py seat_labwc.py" "health.py health.py" "grant.py grant.py" "clipboard_bridge.py clipboard_bridge.py" "uninstall uninstall.sh"`;
- artifacts loop: only `wheelhouse-x86_64` (nwg-shell stays in the seat block);
- `rm -rf "$INSTALL_DIR/venv"` before `python3 -m venv` when `UPGRADE=1`; also `rm -f "$INSTALL_DIR/selkies_launcher.py"`; `rm -rf "$INSTALL_DIR/web" "$INSTALL_DIR/lib"`;
- pip line: `selkies==2.0.0 pixelflux==2.1.0 pcmflux==2.1.0 setuptools aiohttp pulsectl`;
- after install when `UPGRADE=1`: `systemctl --user start styx-agent`, print `Upgraded. Rollback: $INSTALL_DIR/venv/bin/python $INSTALL_DIR/styx_agent.py rollback`, exit 0.

`agent/styx_agent.py`:

```python
def rollback(install_dir: Path = INSTALL_DIR) -> int:
    prev = install_dir.with_name(install_dir.name + ".prev")
    if not (install_dir.is_dir() and prev.is_dir()):
        print(f"No previous install at {prev}")
        return 1
    tmp = install_dir.with_name(install_dir.name + ".swap")
    install_dir.rename(tmp); prev.rename(install_dir); tmp.rename(prev)
    subprocess.run(["systemctl", "--user", "restart", "styx-agent"])
    print("Rolled back; current install is the previous version.")
    return 0
```

and wire `rollback` in `main()`. Delete `agent/selkies_launcher.py` (`git rm`).

- [ ] **Step 4: Run all suites + lint**

```bash
cd backend && .venv/bin/python -m pytest -q && .venv/bin/python -m ruff check app/ tests/ ../agent
cd ../agent && ../backend/.venv/bin/python -m pytest tests -q
bash -n enroll.sh && bash -n ../scripts/build_agent_artifacts.sh
```

Expected: all pass, ruff clean, `bash -n` silent.

- [ ] **Step 5: Commit**

```bash
git add -A agent backend scripts
git commit -m "feat(agent)!: package agent 0.5.0 on selkies 2.0 wheels; enroll --upgrade + rollback

BREAKING CHANGE: agents >= 0.5.0 need the selkies 2.0 wheelhouse; rebuild artifacts first."
```

---

### Task 11: Docs + live acceptance on EliteMini, then GAME-01

**Files:**
- Modify: `docs/` workstation pages (find with `git grep -ln "selkies" docs/ | grep -v superpowers`): add "GNOME seat" section — requirements (GNOME Shell ≥ 46), one-time `styx-agent doctor --grant`, shared-profile caveat (spec §5.6), `seat_shell` fallback, upgrade + rollback commands.
- Modify: `backend/app/config.py:58` comment → `# selkies 2.0 is on PyPI; agents install pinned wheels (scripts/build_agent_artifacts.sh).`

- [ ] **Step 1: Docs edits + commit** — `git commit -m "docs(workstations): GNOME seat, consent grant, upgrade/rollback"`
- [ ] **Step 2: Build artifacts on the server** — `scripts/build_agent_artifacts.sh` → expect `wheelhouse-x86_64.tar.gz` listing `selkies-2.0.0`, `pixelflux-2.1.0`, `pcmflux-2.1.0` wheels.
- [ ] **Step 3: Upgrade EliteMini and verify flags against the installed wheel**

```bash
curl -fsSL https://s.jmolabs.dev/api/enroll/script | bash -s -- --upgrade --server https://s.jmolabs.dev
cd ~/.local/share/styx-agent && venv/bin/python - <<'EOF'
import json, re, pathlib, selkies, engine, seat_gnome
known = set(re.findall(r'"name":\s*"([a-z0-9_]+)"',
        (pathlib.Path(selkies.__file__).parent / "settings.py").read_text()))
cfg = json.loads((pathlib.Path.home() / ".config/styx-agent/config.json").read_text())
cmd, _ = engine.build_selkies_cmd(cfg, 1, {"socket": seat_gnome.SOCKET, "bus": "x"})
bad = [a for a in cmd if a.startswith("--") and a[2:].split("=")[0].replace("-", "_") not in known]
print("UNKNOWN FLAGS:", bad or "none")
EOF
```

Expected: `UNKNOWN FLAGS: none`.
- [ ] **Step 4: `styx-agent doctor --grant`** (or `--grant --local`) → "Consent granted."
- [ ] **Step 5: Run spec §7.3 checklist items 1-9, 11 on EliteMini through Cloudflare**; record pass/fail per item in the PR description. Any fail → stop, open a fix task. Item 9 (browser in seat + physical session at once) is the likeliest failure: GNOME's dock launches browsers with the user's default profile, which the physical session may hold locked. If it fails, the fix task is a seat-only `.desktop` override under the seat's `XDG_DATA_HOME` that adds `--user-data-dir`/`--profile` (as `engine.browser_launch_cmd` does for labwc).
- [ ] **Step 6: GAME-01** — same upgrade + grant; §7.3 item 10 (NVENC load/latency vs 0.4.11) plus one FPS game with pointer lock (relative motion). If relative motion fails, set GAME-01 `seat_shell: labwc` and record it.
- [ ] **Step 7: Merge** `feat/selkies2-phase0-engine` → `main` after both boxes pass; tag via semantic-release.

## Task 1 results

RESIZE=fixed
CONSENT=local

- Headless gnome-shell (virtual-monitor 1920x1080) listed exactly one mode: `'1920x1080@60.000'` (Meta-0). Apply of a second mode failed: `InvalidArgs: Invalid mode '1280x720@60.000' specified`.
- Selkies 2.0.0 connected to `styx-proof-0` (`[HostCapture] host offers no capture protocol; frames come through the xdg-desktop-portal ScreenCast`; `host lacks zwlr_output_manager_v1; capture follows the host's own size`), but logged `Capture for 'primary' (h264) has delivered no frame in 5 s`.
- xdg-desktop-portal-gnome raised its consent window (`Failed to associate portal window with parent window`, 10:40:41) and nothing accepted it; mutter then logged `D-Bus client with active sessions vanished`.
- Portal restore token: mtime before 2026-10-03 08:31:31 (moved aside), absent after the run; no new token written. Old token restored (mtime unchanged).
- Scripted Mutter RemoteDesktop Enter injection from separate gdbus calls cannot work (session `/Session/u2` vanishes when the caller exits: `Object does not exist`); the portal dialog never resolved unattended, so consent stays local.
