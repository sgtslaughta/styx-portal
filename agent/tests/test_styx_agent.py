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
    assert styx_agent.AGENT_VERSION == "0.6.0"


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
    assert h["agent_version"] == "0.6.0"
    assert "needs_consent" not in h
    assert h["selkies_alive"] is True and h["gateway_alive"] is False
    assert h["active_connections"] == 0


def test_settings_change_restart_includes_gateway():
    """Idle-timeout config rides in stream_settings but reaches the gateway only
    through its launch env — so a stream_settings change must relaunch the
    gateway too, else the running gateway keeps stale (idle-less) config."""
    keys = styx_agent.settings_restart_keys({}, {"idle_timeout_s": 60})
    for p in ("selkies", "shell", "clipboard", "gateway"):
        assert p in keys


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


def test_gateway_cmd_passes_seat_dir_only_for_gnome(tmp_path):
    cfg = {"install_dir": str(tmp_path), "selkies_user": "u", "selkies_password": "p",
           "port": 8443, "stream_settings": {"cursor_workaround": True}}
    cmd, env = styx_agent.build_gateway_cmd(cfg, 9000, seat_dir=str(tmp_path))
    assert cmd[-2:] == ["8443", "9000"]
    assert not any(a.endswith("/web") for a in cmd)
    assert env["STYX_GW_SEAT_DIR"] == str(tmp_path)
    assert "STYX_GW_CURSOR_WORKAROUND" not in env
    _, env = styx_agent.build_gateway_cmd(cfg, 9000)
    assert env["STYX_GW_SEAT_DIR"] == ""


def test_gateway_cmd_exposes_state_path(tmp_path):
    _, cfg = _cfg(tmp_path)
    # gateway cmd exposes the state path to the child
    _, env = styx_agent.build_gateway_cmd(cfg, 18444)
    assert env["STYX_GW_STATE"] == str(styx_agent.gw_state_path(cfg))


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


def test_run_config_from_0411_is_accepted(tmp_path, monkeypatch):
    cfg = {"server": "https://x", "agent_token": "t", "workstation_id": "w",
           "port": 8443, "selkies_user": "u", "selkies_password": "p",
           "mode": "seat", "display": "", "seat_socket_index": 2,
           "stream_settings": {"framerate": 60, "h264_crf": 23},
           "install_dir": str(tmp_path), "ca_pin": "", "server_cert": ""}
    monkeypatch.setattr(styx_agent.seat_gnome, "gnome_available", lambda: (True, ""))
    assert styx_agent.pick_seat_shell(cfg) == "gnome"
    p = styx_agent.health_payload(cfg, True, True)
    assert p["agent_version"] == "0.6.0" and "needs_consent" not in p


def test_rollback_swaps_dirs(tmp_path, monkeypatch):
    cur, prev = tmp_path / "styx-agent", tmp_path / "styx-agent.prev"
    cur.mkdir()
    prev.mkdir()
    (cur / "v").write_text("new")
    (prev / "v").write_text("old")
    monkeypatch.setattr(styx_agent.subprocess, "run", lambda *a, **k: None)
    assert styx_agent.rollback(cur) == 0
    assert (cur / "v").read_text() == "old" and (prev / "v").read_text() == "new"
    assert styx_agent.rollback(tmp_path / "missing") == 1


def test_rollback_refuses_stale_swap_dir(tmp_path, monkeypatch):
    cur, prev = tmp_path / "a", tmp_path / "a.prev"
    cur.mkdir()
    prev.mkdir()
    (tmp_path / "a.swap").mkdir()
    monkeypatch.setattr(styx_agent.subprocess, "run", lambda *a, **k: None)
    assert styx_agent.rollback(cur) == 1


def test_rollback_warns_when_restart_fails(tmp_path, monkeypatch, capsys):
    from types import SimpleNamespace
    cur, prev = tmp_path / "a", tmp_path / "a.prev"
    cur.mkdir()
    prev.mkdir()
    monkeypatch.setattr(styx_agent.subprocess, "run",
                        lambda *a, **k: SimpleNamespace(returncode=1))
    assert styx_agent.rollback(cur) == 0
    assert "WARNING" in capsys.readouterr().out


def test_none_to_default_seat_settings_is_not_a_change():
    old = {"video_crf": 25}
    new = {"video_crf": 25, "seat_width": 2560, "seat_height": 1440,
           "seat_shell": "gnome"}
    assert "seat" not in styx_agent.settings_restart_keys(old, new)
    assert "seat" in styx_agent.settings_restart_keys(
        old, {**new, "seat_shell": "labwc"})


def _doctor_env(monkeypatch, tmp_path, mode, gnome, token):
    monkeypatch.setattr(styx_agent.engine, "pick_dri_node", lambda: None)
    monkeypatch.setattr(styx_agent.engine, "resolve_monitor_source", lambda: "m")
    monkeypatch.setattr(styx_agent, "api", lambda *a, **k: {})
    monkeypatch.setattr(styx_agent, "host_tuning_checks", lambda: [])
    monkeypatch.setattr(styx_agent.subprocess, "run",
                        lambda *a, **k: type("R", (), {"stdout": "active\n"})())
    monkeypatch.setattr(styx_agent.socket.socket, "connect_ex", lambda s, a: 0)
    monkeypatch.setattr(styx_agent.seat_gnome, "gnome_available", lambda: gnome)
    inst = tmp_path / "inst"
    (inst / "venv/bin").mkdir(parents=True)
    (inst / "venv/bin/python").write_text("")
    (inst / "venv/bin/selkies").write_text("")
    return {"install_dir": str(inst), "mode": mode, "port": 1}


def test_doctor_no_lib_shim_and_seat_advisories(monkeypatch, tmp_path, capsys):
    cfg = _doctor_env(monkeypatch, tmp_path, "seat", (True, ""), False)
    assert styx_agent.doctor(cfg) == 0
    out = capsys.readouterr().out
    assert "lib shim" not in out
    assert "GNOME seat available" in out
    assert "doctor --grant" not in out


def test_doctor_gnome_missing_is_advisory(monkeypatch, tmp_path, capsys):
    cfg = _doctor_env(monkeypatch, tmp_path, "seat",
                      (False, "gnome-shell not installed"), True)
    assert styx_agent.doctor(cfg) == 0
    out = capsys.readouterr().out
    assert "labwc" in out and "gnome-shell not installed" in out


def test_uninstall_removes_prev(monkeypatch, tmp_path):
    inst = tmp_path / "styx-agent"
    prev = tmp_path / "styx-agent.prev"
    inst.mkdir()
    prev.mkdir()
    monkeypatch.setattr(styx_agent, "INSTALL_DIR", inst)
    monkeypatch.setattr(styx_agent, "CONFIG_PATH", tmp_path / "c.json")
    monkeypatch.setattr(styx_agent, "HOME", tmp_path)
    monkeypatch.setattr(styx_agent.subprocess, "run", lambda *a, **k: None)
    assert styx_agent.uninstall(None) == 0
    assert not inst.exists() and not prev.exists()
