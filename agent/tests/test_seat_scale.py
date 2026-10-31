import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import seat_scale  # noqa: E402


def test_scale_for_dpi():
    for dpi, want in [(None, 1.0), (96, 1.0), (120, 1.5), (144, 1.5), (168, 2.0), (192, 2.0),
                      (240, 3.0), (288, 3.0), (0, 1.0), (72, 1.0), ("x", 1.0)]:
        assert seat_scale.scale_for_dpi(dpi) == want
    assert [seat_scale.dpi_for_scale(v) for v in seat_scale.SCALES] == [96, 144, 192, 288]


def test_read_scale(tmp_path):
    p = tmp_path / "seat-scale"
    assert seat_scale.read_scale(p) == 1.0
    p.write_text("2")
    assert seat_scale.read_scale(p) == 2.0
    p.write_text("1.25")
    assert seat_scale.read_scale(p) == 1.25
    p.write_text("x")
    assert seat_scale.read_scale(p) == 1.0


def test_write_scale_roundtrip_atomic(tmp_path):
    p = tmp_path / "seat-scale"
    seat_scale.write_scale(p, 1.5)
    assert seat_scale.read_scale(p) == 1.5
    seat_scale.write_scale(p, 1)
    assert seat_scale.read_scale(p) == 1.0
    assert not (tmp_path / "seat-scale.tmp").exists()


_MON = ('Meta-0', 'MetaVendor', 'Virtual remote monitor', '0x000001')


def _state(scales=(1.0, 2.0), cur=1.0):
    return (5, [(_MON, [('2560x1252@60.000', 2560, 1252, 60.0, 1.0, list(scales),
                         {'is-current': True, 'is-preferred': True})], {})],
            [(0, 0, cur, 0, True, [_MON], {})], {'layout-mode': 2})


def test_monitors_config():
    assert seat_scale.monitors_config(_state(), 2) == (
        (5, 1, [(0, 0, 2.0, 0, True, [('Meta-0', '2560x1252@60.000', {})])], {}), 2.0)
    assert seat_scale.monitors_config(_state(), 1) == (None, 1.0)
    assert seat_scale.monitors_config(_state(scales=(1.0,)), 2) == (None, 1.0)


def test_pick_scale_only_takes_scales_selkies_shares():
    qhd = (1.0, 1.25, 1.3333333730697632, 1.6666666269302368, 2.0, 2.5, 2.6666667461395264)
    assert seat_scale.pick_scale(qhd, 3) == 2.0         # 2.67 would split GNOME from selkies
    assert seat_scale.pick_scale(qhd, 1.5) == 1.0
    assert seat_scale.pick_scale((1.0, 1.5, 2.0, 3.0), 3) == 3.0
    assert seat_scale.pick_scale((1.0, 1.5, 2.0, 3.0), 2) == 2.0
    assert seat_scale.pick_scale((1.0, 1.5, 2.0, 3.0), 1.5) == 1.5
    assert seat_scale.pick_scale((), 2) == 1.0


class _Bus:
    def __init__(self, state, err=None):
        self.state, self.err, self.applied = state, err, []

    def get_object(self, *_):
        return self

    def GetCurrentState(self):
        if self.err:
            raise self.err
        return self.state

    def ApplyMonitorsConfig(self, *a):
        self.applied.append(a)


@pytest.fixture
def fake_dbus(monkeypatch):
    import types
    m = types.ModuleType("dbus")
    m.Interface = lambda obj, _n: obj
    for n in ("Array", "Struct", "Dictionary"):
        setattr(m, n, lambda v=(), **_k: v)
    for n in ("Int32", "UInt32", "Double", "Boolean"):
        setattr(m, n, lambda v: v)
    monkeypatch.setitem(sys.modules, "dbus", m)


def _run(bus, scale, live=""):
    out = []
    seat_scale.apply_scale(bus, scale, lambda *a: out.append(" ".join(map(str, a))), live)
    return out


def test_apply_scale_applies(fake_dbus):
    bus = _Bus(_state())
    assert _run(bus, 2) == ["scale 2.0 applied"] and len(bus.applied) == 1


def test_apply_scale_already_at_scale_is_silent(fake_dbus):
    bus = _Bus(_state(cur=2.0))
    assert _run(bus, 2) == [] and bus.applied == []


def test_apply_scale_logs_unsupported(fake_dbus):
    out = _run(_Bus(_state(scales=(1.0,))), 2)
    assert len(out) == 1 and "unsupported" in out[0]


def test_apply_scale_never_raises(fake_dbus):
    out = _run(_Bus(_state(), err=RuntimeError("bus gone")), 2)
    assert len(out) == 1 and "bus gone" in out[0]


def test_apply_scale_records_the_scale_it_applied(fake_dbus, tmp_path):
    live = tmp_path / "seat-scale-live"
    bus = _Bus(_state(scales=(1.0, 1.25, 2.0, 2.6666667461395264), cur=2.6666667461395264))
    out = _run(bus, 3, str(live))
    assert seat_scale.read_scale(live) == 2.0
    assert bus.applied[0][2][0][2] == 2.0 and "using 2.0" in out[0]


def test_apply_scale_failure_leaves_live_untouched(fake_dbus, tmp_path):
    live = tmp_path / "seat-scale-live"
    _run(_Bus(_state(), err=RuntimeError("bus gone")), 2, str(live))
    assert not live.exists()
