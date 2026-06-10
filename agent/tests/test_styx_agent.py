import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import styx_agent  # noqa: E402


def _cfg(tmp_path, **kw):
    cfg = {
        "server": "https://192.168.1.10", "agent_token": "tok",
        "workstation_id": "ws1", "port": 8443,
        "selkies_user": "styx", "selkies_password": "pw",
        "display_server": "x11",
        "stream_settings": {"encoder": "x264enc", "framerate": 60,
                            "bitrate_kbps": 16000},
        "selkies_dir": str(tmp_path / "selkies"),
        "ca_pin": "",
        "server_cert": "",
    }
    cfg.update(kw)
    p = tmp_path / "config.json"
    p.write_text(json.dumps(cfg))
    return p, cfg


def test_load_config(tmp_path):
    p, cfg = _cfg(tmp_path)
    loaded = styx_agent.load_config(p)
    assert loaded["port"] == 8443


def test_build_selkies_cmd_x11(tmp_path):
    _, cfg = _cfg(tmp_path)
    cmd, env = styx_agent.build_selkies_cmd(cfg)
    assert cmd[0].endswith("selkies-gstreamer-run")
    assert env["SELKIES_PORT"] == "8443"
    assert env["SELKIES_ENCODER"] == "x264enc"
    assert env["SELKIES_FRAMERATE"] == "60"
    assert env["SELKIES_ENABLE_BASIC_AUTH"] == "true"
    assert env["SELKIES_BASIC_AUTH_PASSWORD"] == "pw"
    assert env["DISPLAY"]  # attaches to a display


def test_build_selkies_cmd_wayland_sets_pixelflux(tmp_path):
    _, cfg = _cfg(tmp_path, display_server="wayland")
    cmd, env = styx_agent.build_selkies_cmd(cfg)
    assert env["PIXELFLUX_WAYLAND"] == "true"


def test_encoder_auto_resolves(monkeypatch, tmp_path):
    _, cfg = _cfg(tmp_path)
    cfg["stream_settings"]["encoder"] = "auto"
    monkeypatch.setattr(styx_agent, "detect_encoder", lambda: "nvh264enc")
    _, env = styx_agent.build_selkies_cmd(cfg)
    assert env["SELKIES_ENCODER"] == "nvh264enc"
