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


def test_caps_fps_default_and_clamp():
    assert "max-framerate=60/1" in seat_portal.caps(1920, 1080)
    assert "width=1920,height=1080,max-framerate=120/1" in seat_portal.caps(1920, 1080, 120)
    assert seat_portal.parse_fps(None) == 60
    assert seat_portal.parse_fps("0") == 1
    assert seat_portal.parse_fps("9999") == 240
    assert seat_portal.parse_fps("junk") == 60


def test_main_argv_fps_flag():
    assert seat_portal.parse_args(["p", "800x600"]) == (800, 600, 60)
    assert seat_portal.parse_args(["p", "800x600", "--max-fps", "120"]) == (800, 600, 120)


def test_max_fps_as_last_arg_falls_back():
    assert seat_portal.parse_args(["p", "800x600", "--max-fps"]) == (800, 600, 60)
