import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import health  # noqa: E402


def _cfg(tmp_path):
    return {"install_dir": str(tmp_path / "styx-agent")}


def test_active_connections_from_gateway_state(tmp_path):
    cfg = _cfg(tmp_path)
    state = health.gw_state_path(cfg)
    state.parent.mkdir(parents=True, exist_ok=True)
    # missing file -> 0
    assert health.active_connections(cfg, gateway_alive=True) == 0
    state.write_text(json.dumps({"active_connections": 2, "ts": 1}))
    assert health.active_connections(cfg, gateway_alive=True) == 2
    # a dead gateway has no viewers, whatever the stale file says
    assert health.active_connections(cfg, gateway_alive=False) == 0
    # garbage -> 0
    state.write_text("not json")
    assert health.active_connections(cfg, gateway_alive=True) == 0
    state.write_text(json.dumps({"active_connections": -3}))
    assert health.active_connections(cfg, gateway_alive=True) == 0


def test_stream_starving_seconds_reports_wait(tmp_path):
    """A viewer connected but no frame has flowed: report seconds since connect."""
    import time
    cfg = _cfg(tmp_path)
    state = health.gw_state_path(cfg)
    state.parent.mkdir(parents=True, exist_ok=True)
    state.write_text(json.dumps({
        "active_connections": 1, "stream_starving": True,
        "starving_since": time.time() - 20, "ts": time.time()}))
    s = health.stream_starving_seconds(cfg, gateway_alive=True)
    assert s is not None and 18 <= s <= 25, s


def test_stream_starving_none_when_not_starving_or_gateway_dead(tmp_path):
    """None once a frame has flowed (flag cleared) or the gateway is down."""
    import time
    cfg = _cfg(tmp_path)
    state = health.gw_state_path(cfg)
    state.parent.mkdir(parents=True, exist_ok=True)
    # frame arrived -> gateway cleared the flag
    state.write_text(json.dumps({
        "active_connections": 1, "stream_starving": False,
        "starving_since": time.time() - 99, "ts": time.time()}))
    assert health.stream_starving_seconds(cfg, gateway_alive=True) is None
    # starving but gateway reported dead -> no viewers to rescue
    state.write_text(json.dumps({
        "stream_starving": True, "starving_since": time.time() - 99}))
    assert health.stream_starving_seconds(cfg, gateway_alive=False) is None
    # unreadable -> None
    state.write_text("not json")
    assert health.stream_starving_seconds(cfg, gateway_alive=True) is None
