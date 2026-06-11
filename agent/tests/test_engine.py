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
    before = set()
    (tmp_path / "wayland-1").touch()
    name = engine.wait_for_wayland_socket(str(tmp_path), before, timeout=1)
    assert name == "wayland-1"
    assert engine.wait_for_wayland_socket(str(tmp_path), {"wayland-1"}, timeout=0.2) is None


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
