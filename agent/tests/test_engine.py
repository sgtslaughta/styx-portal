import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import engine  # noqa: E402


def _cfg(tmp_path, **kw):
    install = tmp_path / "styx-agent"
    (install / "venv/bin").mkdir(parents=True)
    (install / "lib").mkdir()
    (install / "web").mkdir()
    cfg = {
        "server": "https://192.168.1.10", "agent_token": "tok",
        "workstation_id": "ws1", "port": 8443,
        "selkies_user": "styx", "selkies_password": "pw",
        "mode": "mirror", "display": ":1",
        "stream_settings": {"framerate": 60},
        "install_dir": str(install),
        "ca_pin": "", "server_cert": "",
    }
    cfg.update(kw)
    p = tmp_path / "config.json"
    p.write_text(json.dumps(cfg))
    return cfg


def _flags(cmd):
    return {a.split("=", 1)[0] for a in cmd if a.startswith("--")}


def _stub(monkeypatch, dri="", monitor=""):
    monkeypatch.setattr(engine, "pick_dri_node", lambda: dri)
    monkeypatch.setattr(engine, "resolve_monitor_source", lambda: monitor)
    monkeypatch.setattr(engine, "_find_xauthority", lambda c: None)
    monkeypatch.setattr(engine, "query_display_geometry", lambda d, x: (1920, 1080))


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
    assert not any(a.startswith("--wayland-socket-index") for a in cmd)


def test_labwc_seat_cmd_uses_own_compositor(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, mode="seat", display="")
    monkeypatch.setattr(engine, "pick_dri_node", lambda: "")
    monkeypatch.setattr(engine, "resolve_monitor_source", lambda: "")
    cmd, env = engine.build_selkies_cmd(cfg, 18444)
    assert "--wayland=true" in cmd
    assert not any(a.startswith("--wayland-host-display") for a in cmd)
    assert "SELKIES_USE_CPU" not in env and env["SELKIES_AUDIO_ENABLED"] == "false"
    assert "--wayland-socket-index=1" in cmd


def test_labwc_seat_cmd_uses_persisted_socket_index(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, mode="seat", display="", seat_socket_index=3)
    _stub(monkeypatch)
    cmd, _ = engine.build_selkies_cmd(cfg, 18444)
    assert "--wayland-socket-index=3" in cmd


def test_features_off_until_their_phase(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    _stub(monkeypatch)
    cmd, _ = engine.build_selkies_cmd(cfg, 1)
    for f in ("--printing-enabled=false|locked", "--microphone-enabled=false|locked",
              "--webcam-enabled=false|locked", "--gamepad-enabled=false|locked"):
        assert f in cmd


def test_quality_env_prefers_video_keys_and_keeps_old(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, stream_settings={"h264_crf": 22, "video_paintover_crf": 18,
                                          "video_streaming_mode": True})
    _stub(monkeypatch)
    _, env = engine.build_selkies_cmd(cfg, 1)
    assert env["SELKIES_VIDEO_CRF"] == "22"
    assert env["SELKIES_VIDEO_PAINTOVER_CRF"] == "18"
    assert env["SELKIES_VIDEO_STREAMING_MODE"] == "true"


def test_quality_env_ignores_bad_values(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, stream_settings={"video_crf": "abc", "video_paintover_crf": 999})
    _stub(monkeypatch)
    _, env = engine.build_selkies_cmd(cfg, 1)
    assert "SELKIES_VIDEO_CRF" not in env and "SELKIES_VIDEO_PAINTOVER_CRF" not in env
    assert env["SELKIES_VIDEO_STREAMING_MODE"] == "false"   # 2.0 default is true; keep ours


def test_every_flag_exists_in_installed_selkies(tmp_path, monkeypatch):
    """2.0 only WARNS on unknown flags, so a renamed flag would silently no-op."""
    import importlib.util
    import re
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


def test_audio_disabled_when_no_pulse(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    monkeypatch.setattr(engine, "query_display_geometry", lambda d, xa: (1920, 1080))
    monkeypatch.setattr(engine, "_find_xauthority", lambda c: None)
    monkeypatch.setattr(engine, "pick_dri_node", lambda: "")
    monkeypatch.setattr(engine, "resolve_monitor_source", lambda: "")
    cmd, env = engine.build_selkies_cmd(cfg, 18444)
    assert env["SELKIES_AUDIO_ENABLED"] == "false"


def test_wait_for_wayland_socket(tmp_path):
    import time
    (tmp_path / "wayland-1").touch()
    name = engine.wait_for_wayland_socket(str(tmp_path), set(),
                                          since_ts=time.time() + 60, timeout=1)
    assert name == "wayland-1"          # new name counts even with future ts
    assert engine.wait_for_wayland_socket(str(tmp_path), {"wayland-1"},
                                          since_ts=time.time() + 60,
                                          timeout=0.2) is None


def test_wait_for_wayland_socket_excludes_seat_socket(tmp_path):
    # Both sockets are fresh (within the mtime slack). Without exclude, the
    # lexically-first (the seat's own wayland-1) is wrongly returned; with
    # exclude we must get labwc's wayland-2.
    import time
    (tmp_path / "wayland-1").touch()
    (tmp_path / "wayland-2").touch()
    since = time.time() - 60
    assert engine.wait_for_wayland_socket(
        str(tmp_path), {"wayland-1", "wayland-2"}, since_ts=since,
        timeout=1) == "wayland-1"  # default: first match
    assert engine.wait_for_wayland_socket(
        str(tmp_path), {"wayland-1", "wayland-2"}, since_ts=since,
        timeout=1, exclude={"wayland-1"}) == "wayland-2"  # seat excluded


def test_wait_for_wayland_socket_stale_file_rebound(tmp_path):
    # Socket file survived a previous run (name in `before`) but the
    # compositor recreated it after since_ts -> must be detected.
    import time
    (tmp_path / "wayland-1").touch()
    name = engine.wait_for_wayland_socket(str(tmp_path), {"wayland-1"},
                                          since_ts=time.time() - 60, timeout=1)
    assert name == "wayland-1"


def test_guard_default_socket_holds_slot0_and_clears_stale(tmp_path):
    """Guard flocks wayland-0.lock (libwayland's own convention) so neither
    seat compositor can bind the slot that WAYLAND_DISPLAY-less host apps
    fall back to, and removes a stale wayland-0 socket file."""
    import fcntl
    (tmp_path / "wayland-0").touch()        # stale socket from a prior run
    guard = engine.guard_default_socket(str(tmp_path))
    assert guard is not None
    assert not (tmp_path / "wayland-0").exists()
    # Slot now contended: a second taker (compositor) must be refused
    f = open(tmp_path / "wayland-0.lock", "a+")
    try:
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
            raised = False
        except OSError:
            raised = True
        assert raised
    finally:
        f.close()
    guard.close()


def test_guard_default_socket_yields_to_live_owner(tmp_path):
    """If a real Wayland session already holds the slot-0 lock, back off."""
    import fcntl
    owner = open(tmp_path / "wayland-0.lock", "a+")
    fcntl.flock(owner, fcntl.LOCK_EX | fcntl.LOCK_NB)
    try:
        assert engine.guard_default_socket(str(tmp_path)) is None
    finally:
        owner.close()


def test_pick_dri_node(tmp_path, monkeypatch):
    dri = tmp_path / "dri"
    dri.mkdir()
    (dri / "renderD128").touch()
    monkeypatch.setattr(engine, "DRI_DIR", str(dri))
    assert engine.pick_dri_node().endswith("renderD128")
    monkeypatch.setattr(engine, "DRI_DIR", str(tmp_path / "nope"))
    assert engine.pick_dri_node() == ""


def test_pick_free_port():
    p = engine.pick_free_port()
    assert 1024 < p < 65536
