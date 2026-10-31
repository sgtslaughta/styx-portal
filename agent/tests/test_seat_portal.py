import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
try:
    import seat_portal  # needs system dbus-python + PyGObject + Gst typelib
except (ImportError, ValueError):
    pytest.skip("seat_portal needs dbus-python/PyGObject/Gst", allow_module_level=True)


def test_selftest_method_tables():
    assert seat_portal.selftest() == 0


def test_parse_size():
    assert seat_portal.parse_size("2552x1294") == (2552, 1294)
    for bad in ("0x10", "axb", "1920"):
        with pytest.raises(ValueError):
            seat_portal.parse_size(bad)


def test_ordered_fixes_swapped_press_release():
    # xdg-desktop-portal delivered 'e' as release, press: Mutter kept it down.
    s, sent = type("S", (), {"down": set(), "early": {}})(), []
    send = lambda code, down: sent.append((code, down))  # noqa: E731
    seat_portal._ordered(s, "K", 101, False, send)   # early release: held back
    assert sent == []
    seat_portal._ordered(s, "K", 101, True, send)    # its press: press + release
    assert sent == [(101, True), (101, False)]
    sent.clear()
    seat_portal._ordered(s, "K", 32, True, send)     # in-order pair untouched
    seat_portal._ordered(s, "K", 32, False, send)
    assert sent == [(32, True), (32, False)]
    sent.clear()
    seat_portal._ordered(s, "K", 7, False, send)     # stale stray release
    s.early[("K", 7)] -= 1
    seat_portal._ordered(s, "K", 7, True, send)      # later hold stays held
    assert sent == [(7, True)]
