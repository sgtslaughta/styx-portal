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


WRAP = 16


class _Relay:
    """Upstream _VideoRelay cut down to what _forward reads."""
    def __init__(self, owner=True, lag=0.0, room=True):
        self.numbered, self.since_key, self.sent = False, 1, {7}
        self.lost_first, self.gauged, self.lost = None, False, []
        self.ws, self.display_id = object(), "primary"
        self.server = SimpleNamespace(_owns_display=lambda ws, d: owner)
        self.lag_s, self.room = lag, room

    def _lose(self, frame_id):
        self.lost.append(frame_id)

    def _repair(self):
        return False

    def _lag(self):
        return self.lag_s

    def _room(self):
        return self.room

    def _anchor_room(self):
        return False

    def _end_lost(self):
        self.lost_first = None

    def _forward(self, frame_id, reference, anchor=False):
        return "upstream"


def _gated(**kw):
    cls = type("R", (_Relay,), {})
    shallow_pipe.owner_gate(cls, SimpleNamespace(FRAME_NUM_WRAP=WRAP), "2.1.0")
    return cls(**kw)


def test_owner_over_lag_skips_delta():
    r = _gated(lag=0.2)
    assert r._forward(8, 7) is False and r.lost == [8]


def test_owner_under_lag_passes():
    assert _gated(lag=0.05)._forward(8, 7) is True


def test_owner_without_floor_passes():
    assert _gated(lag=0.0)._forward(8, 7) is True


def test_owner_anchor_and_kept_never_skipped():
    assert _gated(lag=5)._forward(8, 7, anchor=True) is True
    r = _gated(lag=5)
    r.numbered, r.since_key = True, WRAP
    assert r._forward(8, 7) is True and r.lost == []


def test_owner_sets_gauged():
    r = _gated(lag=0.0)
    r._forward(8, 7)
    assert r.gauged is True


def test_viewer_rules_unchanged():
    r = _gated(owner=False, room=False)
    assert r._forward(8, 7) is False and r.lost == [8]
    assert _gated(owner=False, room=True)._forward(8, 7) is True


def test_missing_reference_still_repairs():
    r = _gated(lag=0.0)
    assert r._forward(8, 99) is False and r.lost == [8]


def test_version_mismatch_skips_patch():
    cls = type("R", (_Relay,), {})
    shallow_pipe.owner_gate(cls, SimpleNamespace(FRAME_NUM_WRAP=WRAP), "2.2.0")
    assert cls()._forward(8, 7) == "upstream"
