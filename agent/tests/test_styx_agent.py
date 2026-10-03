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
        "mode": "mirror", "display": ":1",
        "stream_settings": {"framerate": 60},
        "install_dir": str(tmp_path / "styx-agent"),
        "ca_pin": "", "server_cert": "",
    }
    cfg.update(kw)
    p = tmp_path / "config.json"
    p.write_text(json.dumps(cfg))
    return p, cfg


def test_load_config(tmp_path):
    p, _ = _cfg(tmp_path)
    assert styx_agent.load_config(p)["port"] == 8443


def test_agent_version_bumped():
    assert styx_agent.AGENT_VERSION == "0.4.11"


def test_gateway_cmd_secrets_via_env(tmp_path):
    _, cfg = _cfg(tmp_path)
    cmd, env = styx_agent.build_gateway_cmd(cfg, 18444)
    assert cmd[0].endswith("venv/bin/python")
    assert cmd[1].endswith("gateway.py")
    assert cmd[2] == "8443"          # LAN port
    assert cmd[3] == "18444"         # loopback selkies
    assert env["STYX_GW_USER"] == "styx"
    assert env["STYX_GW_PASSWORD"] == "pw"
    assert not any("pw" in a for a in cmd)


def test_gateway_cmd_passes_idle_config_via_env(tmp_path):
    """Idle timeout config rides in stream_settings (delivered each heartbeat);
    build_gateway_cmd forwards it to the gateway as env."""
    _, cfg = _cfg(tmp_path, stream_settings={
        "framerate": 60, "idle_timeout_s": 600,
        "idle_warn_lead_s": 45, "idle_timeout_enabled": True})
    _, env = styx_agent.build_gateway_cmd(cfg, 18444)
    assert env["STYX_GW_IDLE_TIMEOUT_S"] == "600"
    assert env["STYX_GW_IDLE_WARN_S"] == "45"
    assert env["STYX_GW_IDLE_ENABLED"] == "1"


def test_gateway_cmd_idle_disabled_when_absent_or_off(tmp_path):
    _, cfg = _cfg(tmp_path, stream_settings={
        "framerate": 60, "idle_timeout_s": 600, "idle_timeout_enabled": False})
    _, env = styx_agent.build_gateway_cmd(cfg, 18444)
    assert env["STYX_GW_IDLE_ENABLED"] == ""       # off -> gateway skips
    # missing entirely -> disabled, safe default
    _, cfg2 = _cfg(tmp_path, stream_settings={"framerate": 60})
    _, env2 = styx_agent.build_gateway_cmd(cfg2, 18444)
    assert env2["STYX_GW_IDLE_ENABLED"] == ""


def test_health_payload_reports_mode_and_engine(tmp_path):
    _, cfg = _cfg(tmp_path, mode="seat")
    h = styx_agent.health_payload(cfg, selkies_alive=True, gateway_alive=False)
    assert h["mode"] == "seat"
    assert h["engine"] == "pixelflux"
    assert h["agent_version"] == "0.4.11"
    assert h["selkies_alive"] is True and h["gateway_alive"] is False
    assert h["active_connections"] == 0


def test_settings_change_restart_includes_gateway():
    """Idle-timeout config rides in stream_settings but reaches the gateway only
    through its launch env — so a stream_settings change must relaunch the
    gateway too, else the running gateway keeps stale (idle-less) config."""
    assert "gateway" in styx_agent.SETTINGS_CHANGE_RESTART
    for p in ("selkies", "shell", "clipboard"):
        assert p in styx_agent.SETTINGS_CHANGE_RESTART


def test_drop_clients_restarts_gateway():
    from unittest.mock import MagicMock
    gw = MagicMock()
    gw.poll.return_value = None  # alive
    procs = {"selkies": MagicMock(), "gateway": gw, "shell": None}

    styx_agent.drop_clients(procs)

    gw.terminate.assert_called_once()
    gw.wait.assert_called_once()  # graceful shutdown attempted before respawn
    # cleared so the supervisor loop respawns it (dropping all stream clients)
    assert procs["gateway"] is None


def test_drop_clients_noop_when_gateway_dead():
    from unittest.mock import MagicMock
    gw = MagicMock()
    gw.poll.return_value = 0  # already exited
    procs = {"gateway": gw}

    styx_agent.drop_clients(procs)

    gw.terminate.assert_not_called()
    assert procs["gateway"] is None


# === Stream-start watchdog (frameless viewer -> restart engine) ===

def test_restart_engine_tears_down_selkies_shell_clipboard():
    """Frameless-recovery restart rebuilds the whole seat (new Wayland socket),
    not just selkies — else labwc/clipboard keep the dead compositor's socket."""
    from unittest.mock import MagicMock

    def alive():
        p = MagicMock()
        p.poll.return_value = None
        return p

    procs = {"selkies": alive(), "shell": alive(), "clipboard": alive(),
             "gateway": alive()}
    gw = procs["gateway"]

    styx_agent._restart_engine(procs)

    for key in ("selkies", "shell", "clipboard"):
        assert procs[key] is None
    # gateway is the viewer's link home — must survive so the browser reconnects
    gw.terminate.assert_not_called()
    assert procs["gateway"] is gw


def test_host_tuning_checks_governor(monkeypatch, tmp_path):
    gov = tmp_path / "scaling_governor"
    gov.write_text("powersave\n")
    monkeypatch.setattr(styx_agent, "GOVERNOR_PATH", gov)
    monkeypatch.setattr(styx_agent.shutil, "which", lambda _: None)
    rows = styx_agent.host_tuning_checks()
    label, ok, detail = next(r for r in rows if "governor" in r[0])
    assert not ok and "performance" in detail


def test_host_tuning_checks_all_good(monkeypatch, tmp_path):
    gov = tmp_path / "scaling_governor"
    gov.write_text("performance\n")
    monkeypatch.setattr(styx_agent, "GOVERNOR_PATH", gov)
    monkeypatch.setattr(styx_agent.shutil, "which", lambda _: "/usr/bin/nvidia-smi")
    monkeypatch.setattr(styx_agent.subprocess, "run", lambda *a, **k: type(
        "R", (), {"stdout": "Enabled\n", "returncode": 0})())
    assert all(ok for _, ok, _ in styx_agent.host_tuning_checks())


def test_gateway_cmd_has_no_web_dir_and_passes_cursor_flag(tmp_path):
    cfg = {"install_dir": str(tmp_path), "port": 8443, "selkies_user": "u",
           "selkies_password": "p", "stream_settings": {"cursor_workaround": True}}
    cmd, env = styx_agent.build_gateway_cmd(cfg, 1234)
    assert cmd[-2:] == ["8443", "1234"]
    assert not any(a.endswith("/web") for a in cmd)
    assert env["STYX_GW_CURSOR_WORKAROUND"] == "1"


def test_gateway_cmd_exposes_state_path(tmp_path):
    _, cfg = _cfg(tmp_path)
    # gateway cmd exposes the state path to the child
    _, env = styx_agent.build_gateway_cmd(cfg, 18444)
    assert env["STYX_GW_STATE"] == str(styx_agent.gw_state_path(cfg))
