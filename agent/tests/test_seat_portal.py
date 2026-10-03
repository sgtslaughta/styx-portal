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
