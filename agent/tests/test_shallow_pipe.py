import logging
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import shallow_pipe  # noqa: E402


class _Steer:
    pass


def _wm(queued):
    """Stand-in for selkies.websockets_mode: the two helpers queue_ms reads."""
    return SimpleNamespace(_queued_round_trips=lambda acks, bps: queued,
                           _path_rate=lambda acks, floor: 1.0)


def _state():
    return {"rtt_floor_ms": 60, "link_tick_at": 0,
            "link_acks": [(1, 100, 1000), (2, 90, 2000), (3, 120, 3000)]}


def _server():
    class Server:
        def _steer_bitrate_to_link(self, display_id, state, now):
            if state:
                state["link_tick_at"] = now
                state["link_kbps"] = 8000
    return Server


def test_queue_ms_least_minus_floor():
    assert shallow_pipe.queue_ms(_state(), _wm([100, 90, 120])) == 30


def test_queue_ms_none_without_acks_or_floor():
    wm = _wm([100])
    assert shallow_pipe.queue_ms({}, wm) is None
    assert shallow_pipe.queue_ms({**_state(), "rtt_floor_ms": 0}, wm) is None


def test_trace_tolerates_empty_state(caplog):
    cls = _server()
    shallow_pipe.trace_steer(cls, _wm([]), _Steer)
    with caplog.at_level(logging.INFO, logger="ws"):
        cls()._steer_bitrate_to_link("primary", {}, 1.0)
    assert not [r for r in caplog.records if "STYX-CC" in r.getMessage()]


def test_trace_logs_line(caplog):
    cls = _server()
    shallow_pipe.trace_steer(cls, _wm([100, 90, 120]), _Steer)
    with caplog.at_level(logging.INFO, logger="ws"):
        cls()._steer_bitrate_to_link("primary", _state(), 5.0)
    msgs = [r.getMessage() for r in caplog.records if "STYX-CC" in r.getMessage()]
    assert len(msgs) == 1 and msgs[0].startswith("STYX-CC primary q=30 floor=60 ")
    assert "rate=8000" in msgs[0]


def test_trace_sets_steer_q():
    cls = _server()
    shallow_pipe.trace_steer(cls, _wm([100, 90, 120]), _Steer)
    state = _state()
    cls()._steer_bitrate_to_link("primary", state, 5.0)
    assert state["link_steer"].styx_q_ms == 30


def test_queue_ms_thin_window_judged_with_acks_before():
    # One fresh ack (t=3, rtt 120) is judged with the earlier ones, as upstream does.
    state = {**_state(), "link_tick_at": 2.5}
    assert shallow_pipe.queue_ms(state, _wm([100, 90, 120])) == 30
