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


class _UpSteer:
    APP_LIMITED = 0.5

    def __init__(self):
        self._tick_at = None

    def target(self, *a, **kw):
        return "upstream"


def _smooth():
    cls = type("S", (_UpSteer,), {})
    shallow_pipe.smooth_steer(cls)
    return cls()


def _t(s, q, cur, d_kbps, offered_kbps, now=0.0):
    if q is not None:
        s.styx_q_ms = q
    return s.target(cur, 16000, 1000, d_kbps * 1000, 0.0, now, 0.0,
                    None if offered_kbps is None else offered_kbps * 1000)


def test_calm_probes_gently():
    s, cur, out = _smooth(), 8000, []
    for i in range(10):
        cur = _t(s, 0, cur, 8000, cur, now=i * 0.5)
        out.append(cur)
    assert out[0] > 8000 and max(out) <= 8400


def test_ease_is_proportional():
    assert _t(_smooth(), 60, 12000, 10000, 12000) == 8000


def test_ease_never_raises():
    assert _t(_smooth(), 60, 5000, 10000, 5000) == 5000


def test_collapse_cuts_once_then_holds():
    # Real ticks are 0.5 s apart: the draining queue still reads on the next one.
    s = _smooth()
    assert _t(s, 200, 8000, 8000, 8000, now=10.0) == 4000
    assert _t(s, 200, 4000, 3000, 4000, now=10.5) == 4000
    assert _t(s, 150, 4000, 3000, 4000, now=10.8) == 4000


def test_queue_teaches_capacity():
    s = _smooth()
    s.styx_known_kbps = 16000
    _t(s, 60, 12000, 6000, 12000)
    assert s.styx_known_kbps == 6000


def test_recovers_fast_below_known_then_gently():
    s = _smooth()
    s.styx_known_kbps, s._tick_at = 6000, 0.0
    assert _t(s, 0, 2500, 2500, 2500, now=1.0) == 2500 * 1.15
    assert _t(s, 0, 5500, 5500, 5500, now=2.0) == 5500 * 1.05


def test_still_screen_holds():
    s = _smooth()
    s.styx_known_kbps = 9000
    assert _t(s, 0, 8000, 100, 100) == 8000 and s.styx_known_kbps == 9000


def test_no_measure_holds():
    assert _t(_smooth(), None, 8000, 8000, 8000) == 8000


def test_never_below_floor_or_above_ceiling():
    assert _t(_smooth(), 1000, 8000, 10, 8000) == 1000
    s, cur = _smooth(), 15900
    for i in range(10):
        cur = _t(s, 0, cur, 50000, cur, now=i * 0.5)
    assert cur <= 16000


def test_still_screen_never_holds_above_known():
    # 0.9.14 hotel run: rate sat at the 16000 ceiling on a still screen over a ~6 Mbps path.
    s = _smooth()
    s.styx_known_kbps = 6000
    assert _t(s, 0, 16000, 100, 100) == 6300


def test_known_capacity_survives_reconnect():
    # selkies' _forget_path drops link_steer on reconnect; the path's capacity is kept per display.
    shallow_pipe.KNOWN_KBPS.clear()
    cls = _server()
    shallow_pipe.trace_steer(cls, _wm([100, 90, 120]), _Steer)
    state = _state()
    cls()._steer_bitrate_to_link("primary", state, 5.0)
    state["link_steer"].styx_known_kbps = 5400
    cls()._steer_bitrate_to_link("primary", state, 6.0)     # remembered after the tick
    fresh = {**_state(), "link_tick_at": 0}                  # reconnect: new state, no steer
    cls()._steer_bitrate_to_link("primary", fresh, 7.0)
    assert fresh["link_steer"].styx_known_kbps == 5400
