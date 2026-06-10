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


def test_build_selkies_cmd_uses_cli_flags(tmp_path):
    _, cfg = _cfg(tmp_path)
    cmd, env = styx_agent.build_selkies_cmd(cfg, ":0")
    assert cmd[0].endswith("selkies-gstreamer-run")
    # selkies-gstreamer 1.6.x reads CLI flags, not env vars
    assert "--addr=0.0.0.0" in cmd
    assert "--port=8443" in cmd
    assert "--encoder=x264enc" in cmd
    # secret must travel via env, never argv (/proc/<pid>/cmdline is readable)
    assert not any("pw" in a for a in cmd)
    assert env["SELKIES_BASIC_AUTH_USER"] == "styx"
    assert env["SELKIES_BASIC_AUTH_PASSWORD"] == "pw"
    assert env["DISPLAY"] == ":0"
    assert "PULSE_SERVER" in env
    # bundled interpreter must ignore the user's site-packages
    assert env["PYTHONNOUSERSITE"] == "1"
    assert "PYTHONPATH" not in env


def test_display_override_wins_over_wayland(tmp_path):
    _, cfg = _cfg(tmp_path, display_server="wayland", display=":1")
    start_xvfb, display = styx_agent.display_plan(cfg)
    assert start_xvfb is False
    assert display == ":1"


def test_xauthority_set_for_live_display(tmp_path):
    xa = tmp_path / "xauth"; xa.write_bytes(b"cookie")
    _, cfg = _cfg(tmp_path, display=":1", xauthority=str(xa))
    _, env = styx_agent.build_selkies_cmd(cfg, ":1", use_xauth=True)
    assert env["XAUTHORITY"] == str(xa)


def test_xauthority_skipped_for_xvfb(tmp_path):
    xa = tmp_path / "xauth"; xa.write_bytes(b"cookie")
    _, cfg = _cfg(tmp_path, xauthority=str(xa))
    _, env = styx_agent.build_selkies_cmd(cfg, ":100", use_xauth=False)
    assert "XAUTHORITY" not in env


def test_display_plan_defaults_to_own_session(tmp_path, monkeypatch):
    # No --display override: own virtual desktop regardless of host session type.
    monkeypatch.setenv("DISPLAY", ":0")
    _, cfg = _cfg(tmp_path)
    start_xvfb, display = styx_agent.display_plan(cfg)
    assert start_xvfb is True
    assert display == ":100"


def test_display_plan_mirror_override(tmp_path):
    _, cfg = _cfg(tmp_path, display=":1")
    start_xvfb, display = styx_agent.display_plan(cfg)
    assert start_xvfb is False
    assert display == ":1"


def test_encoder_auto_resolves(monkeypatch, tmp_path):
    _, cfg = _cfg(tmp_path)
    cfg["stream_settings"]["encoder"] = "auto"
    monkeypatch.setattr(styx_agent, "detect_encoder", lambda _d: "nvh264enc")
    cmd, env = styx_agent.build_selkies_cmd(cfg, ":0")
    assert "--encoder=nvh264enc" in cmd
    assert env["SELKIES_ENCODER"] == "nvh264enc"


def test_detect_encoder_probes_bundled_gst(monkeypatch):
    # vah264enc present in gst -> chosen over x264enc; HW-first ordering
    monkeypatch.setattr(styx_agent, "_gst_has_element",
                        lambda d, e: e in ("vah264enc", "x264enc"))
    assert styx_agent.detect_encoder("/x") == "vah264enc"
    # only x264enc available (the real portable-tarball case) -> x264enc
    monkeypatch.setattr(styx_agent, "_gst_has_element",
                        lambda d, e: e == "x264enc")
    assert styx_agent.detect_encoder("/x") == "x264enc"
