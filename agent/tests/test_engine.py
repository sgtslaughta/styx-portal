import json
import sys
from pathlib import Path

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


def test_mirror_cmd_attaches_display_and_locks_resolution(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    monkeypatch.setattr(engine, "query_display_geometry", lambda d, xa: (2560, 1440))
    monkeypatch.setattr(engine, "_find_xauthority", lambda c: "/tmp/xa")
    monkeypatch.setattr(engine, "pick_dri_node", lambda: "/dev/dri/renderD128")
    monkeypatch.setattr(engine, "resolve_monitor_source", lambda: "out.monitor")
    cmd, env = engine.build_selkies_cmd(cfg, 18444, 18445)
    assert cmd[0].endswith("venv/bin/python")
    assert cmd[1].endswith("selkies_launcher.py")
    assert "--port=18444" in cmd
    assert "--control-port=18445" in cmd
    assert "--is-manual-resolution-mode=true" in cmd
    assert "--manual-width=2560" in cmd and "--manual-height=1440" in cmd
    assert "--dri-node=/dev/dri/renderD128" in cmd
    assert "--audio-device-name=out.monitor" in cmd
    assert env["DISPLAY"] == ":1"
    assert env["XAUTHORITY"] == "/tmp/xa"
    assert "PIXELFLUX_WAYLAND" not in env
    assert env["LD_LIBRARY_PATH"].startswith(cfg["install_dir"] + "/lib")
    assert env["PYTHONNOUSERSITE"] == "1"
    # secrets never in argv
    assert not any("pw" in a for a in cmd)


def test_seat_cmd_uses_wayland_backend(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, mode="seat", display="")
    monkeypatch.setattr(engine, "pick_dri_node", lambda: "/dev/dri/renderD128")
    monkeypatch.setattr(engine, "resolve_monitor_source", lambda: "styx-seat.monitor")
    cmd, env = engine.build_selkies_cmd(cfg, 18444, 18445)
    assert env["PIXELFLUX_WAYLAND"] == "true"
    assert env["DRINODE"] == "/dev/dri/renderD128"
    assert "DISPLAY" not in env
    assert "--is-manual-resolution-mode=true" not in cmd
    assert "--wayland-socket-index=1" in cmd      # default until detected


def test_seat_cmd_uses_persisted_socket_index(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, mode="seat", display="", seat_socket_index=3)
    monkeypatch.setattr(engine, "pick_dri_node", lambda: "")
    monkeypatch.setattr(engine, "resolve_monitor_source", lambda: "")
    cmd, _ = engine.build_selkies_cmd(cfg, 18444, 18445)
    assert "--wayland-socket-index=3" in cmd


def test_seat_cmd_without_gpu_falls_back_to_cpu(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, mode="seat", display="")
    monkeypatch.setattr(engine, "pick_dri_node", lambda: "")
    monkeypatch.setattr(engine, "resolve_monitor_source", lambda: "styx-seat.monitor")
    cmd, env = engine.build_selkies_cmd(cfg, 18444, 18445)
    assert "DRINODE" not in env
    assert not any(a.startswith("--dri-node") for a in cmd)


def test_audio_disabled_when_no_pulse(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    monkeypatch.setattr(engine, "query_display_geometry", lambda d, xa: (1920, 1080))
    monkeypatch.setattr(engine, "_find_xauthority", lambda c: None)
    monkeypatch.setattr(engine, "pick_dri_node", lambda: "")
    monkeypatch.setattr(engine, "resolve_monitor_source", lambda: "")
    cmd, env = engine.build_selkies_cmd(cfg, 18444, 18445)
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


def test_pick_launcher_prefers_grid_then_fuzzel(monkeypatch):
    import shutil
    monkeypatch.setattr(shutil, "which",
                        lambda n: "/usr/bin/" + n if n == "nwg-drawer" else None)
    assert engine.pick_launcher() == "nwg-drawer"
    monkeypatch.setattr(shutil, "which",
                        lambda n: "/usr/bin/fuzzel" if n == "fuzzel" else None)
    assert engine.pick_launcher() == "fuzzel"
    monkeypatch.setattr(shutil, "which", lambda n: None)
    assert engine.pick_launcher() == ""


def test_pick_file_manager_detection_order(monkeypatch):
    import shutil
    monkeypatch.setattr(shutil, "which",
                        lambda n: "/usr/bin/" + n if n in ("thunar", "nemo") else None)
    # nemo ranks above thunar in the order
    assert engine.pick_file_manager() == "nemo"
    monkeypatch.setattr(shutil, "which", lambda n: None)
    assert engine.pick_file_manager() == ""


def test_scan_desktop_entries_parses_and_filters(tmp_path):
    apps = tmp_path / "applications"
    apps.mkdir()
    (apps / "firefox.desktop").write_text(
        "[Desktop Entry]\nName=Firefox\nExec=firefox %u\nType=Application\n")
    (apps / "hidden.desktop").write_text(
        "[Desktop Entry]\nName=Secret\nExec=secret\nNoDisplay=true\n")
    (apps / "noexec.desktop").write_text(
        "[Desktop Entry]\nName=Broken\nType=Application\n")
    entries = engine.scan_desktop_entries([str(apps)])
    assert entries == [("Firefox", "firefox")]   # field code stripped, others filtered


def test_scan_desktop_entries_skips_missing_dirs():
    assert engine.scan_desktop_entries(["/no/such/dir"]) == []
