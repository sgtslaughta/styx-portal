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
    assert styx_agent.AGENT_VERSION == "0.4.2"


def test_gateway_cmd_secrets_via_env(tmp_path):
    _, cfg = _cfg(tmp_path)
    cmd, env = styx_agent.build_gateway_cmd(cfg, 18444)
    assert cmd[0].endswith("venv/bin/python")
    assert cmd[1].endswith("gateway.py")
    assert cmd[2].endswith("/web")
    assert cmd[3] == "8443"          # LAN port
    assert cmd[4] == "18444"         # loopback selkies
    assert env["STYX_GW_USER"] == "styx"
    assert env["STYX_GW_PASSWORD"] == "pw"
    assert not any("pw" in a for a in cmd)


def test_health_payload_reports_mode_and_engine(tmp_path):
    _, cfg = _cfg(tmp_path, mode="seat")
    h = styx_agent.health_payload(cfg, selkies_alive=True, gateway_alive=False)
    assert h["mode"] == "seat"
    assert h["engine"] == "pixelflux"
    assert h["agent_version"] == "0.4.2"
    assert h["selkies_alive"] is True and h["gateway_alive"] is False
    assert h["active_connections"] == 0


def test_active_connections_from_gateway_state(tmp_path):
    _, cfg = _cfg(tmp_path)
    state = styx_agent.gw_state_path(cfg)
    state.parent.mkdir(parents=True, exist_ok=True)
    # missing file -> 0
    assert styx_agent.active_connections(cfg, gateway_alive=True) == 0
    state.write_text(json.dumps({"active_connections": 2, "ts": 1}))
    assert styx_agent.active_connections(cfg, gateway_alive=True) == 2
    # a dead gateway has no viewers, whatever the stale file says
    assert styx_agent.active_connections(cfg, gateway_alive=False) == 0
    # garbage -> 0
    state.write_text("not json")
    assert styx_agent.active_connections(cfg, gateway_alive=True) == 0
    state.write_text(json.dumps({"active_connections": -3}))
    assert styx_agent.active_connections(cfg, gateway_alive=True) == 0
    # gateway cmd exposes the state path to the child
    _, env = styx_agent.build_gateway_cmd(cfg, 18444)
    assert env["STYX_GW_STATE"] == str(state)


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
