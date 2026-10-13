import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import seat_scale  # noqa: E402


def test_scale_for_dpi():
    for dpi, want in [(None, 1), (96, 1), (144, 1), (168, 2), (192, 2), (288, 2), (0, 1)]:
        assert seat_scale.scale_for_dpi(dpi) == want


def test_read_scale(tmp_path):
    p = tmp_path / "seat-scale"
    assert seat_scale.read_scale(p) == 1
    p.write_text("2")
    assert seat_scale.read_scale(p) == 2
    p.write_text("x")
    assert seat_scale.read_scale(p) == 1


def test_write_scale_roundtrip_atomic(tmp_path):
    p = tmp_path / "seat-scale"
    seat_scale.write_scale(p, 2)
    assert p.read_text() == "2" and seat_scale.read_scale(p) == 2
    seat_scale.write_scale(p, 1)
    assert seat_scale.read_scale(p) == 1
    assert not (tmp_path / "seat-scale.tmp").exists()


_MON = ('Meta-0', 'MetaVendor', 'Virtual remote monitor', '0x000001')


def _state(scales=(1.0, 2.0), cur=1.0):
    return (5, [(_MON, [('2560x1252@60.000', 2560, 1252, 60.0, 1.0, list(scales),
                         {'is-current': True, 'is-preferred': True})], {})],
            [(0, 0, cur, 0, True, [_MON], {})], {'layout-mode': 2})


def test_monitors_config():
    assert seat_scale.monitors_config(_state(), 2) == (
        5, 1, [(0, 0, 2.0, 0, True, [('Meta-0', '2560x1252@60.000', {})])], {})
    assert seat_scale.monitors_config(_state(), 1) is None
    assert seat_scale.monitors_config(_state(scales=(1.0,)), 2) is None


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


def _run(bus, scale):
    out = []
    seat_scale.apply_scale(bus, scale, lambda *a: out.append(" ".join(map(str, a))))
    return out


def test_apply_scale_applies(fake_dbus):
    bus = _Bus(_state())
    assert _run(bus, 2) == ["scale 2 applied"] and len(bus.applied) == 1


def test_apply_scale_already_at_scale_is_silent(fake_dbus):
    bus = _Bus(_state(cur=2.0))
    assert _run(bus, 2) == [] and bus.applied == []


def test_apply_scale_logs_unsupported(fake_dbus):
    out = _run(_Bus(_state(scales=(1.0,))), 2)
    assert len(out) == 1 and "unsupported" in out[0]


def test_apply_scale_never_raises(fake_dbus):
    out = _run(_Bus(_state(), err=RuntimeError("bus gone")), 2)
    assert len(out) == 1 and "bus gone" in out[0]
