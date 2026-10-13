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
