import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import refit  # noqa: E402


def test_clamp_bounds_and_even():
    assert refit.clamp(320, 200) == (640, 480)
    assert refit.clamp(7680, 4320) == (4096, 2304)
    assert refit.clamp(2553, 1295) == (2552, 1294)


def test_parse_resize():
    assert refit.parse_resize("r,2552x1294,primary") == (2552, 1294)
    assert refit.parse_resize("r,1920x1080") == (1920, 1080)
    for bad in ("r,1920,1080", "r,axb", "kd,65", "r,99999999x1", b"r,1x1", None):
        assert refit.parse_resize(bad) is None


def test_decide_tolerance_and_unknown_current():
    assert refit.decide((2560, 1300), (2552, 1294), 0, 100) is None      # within 16 px
    assert refit.decide((2552, 1294), (1920, 1080), 0, 100) == (2552, 1294)
    assert refit.decide((2552, 1294), None, 0, 100) == (2552, 1294)       # no seat-size yet
    assert refit.decide((100, 100), (640, 480), 0, 100) is None           # clamps to current


def test_decide_rate_limited():
    assert refit.decide((2552, 1294), (1920, 1080), 98, 100) == 1.0       # 2 s after last: wait 1 s
    assert refit.decide((2552, 1294), (1920, 1080), 96, 100) == (2552, 1294)
    assert refit.decide((1920, 1080), (1920, 1080), 98, 100) is None       # same size: nothing


def test_size_file_roundtrip_and_request(tmp_path):
    f = tmp_path / "seat-size"
    assert refit.read_size(f) is None
    refit.write_size(f, 2552, 1294)
    assert refit.read_size(f) == (2552, 1294)
    r = tmp_path / "refit-request"
    assert not refit.pending(r)
    refit.request(r, 1920, 1080)
    assert refit.pending(r) and refit.read_size(r) == (1920, 1080)
    refit.clear_request(r)
    refit.clear_request(r)                                              # idempotent
    assert not refit.pending(r)


def test_wait_for_request_returns_request_or_times_out(tmp_path):
    r = tmp_path / "refit-request"
    t = {"now": 0.0}
    clock = lambda: t["now"]                                            # noqa: E731

    def sleep(s):
        t["now"] += s
    assert refit.wait_for_request(r, 1.0, sleep=sleep, clock=clock) is None
    assert t["now"] >= 1.0
    refit.request(r, 1920, 1080)
    assert refit.wait_for_request(r, 1.0, sleep=sleep, clock=clock) == (1920, 1080)


def test_wait_for_request_clears_garbage(tmp_path):
    r = tmp_path / "refit-request"
    r.write_text("garbage")
    t = {"now": 0.0}
    assert refit.wait_for_request(r, 0.5, sleep=lambda s: t.update(now=t["now"] + s),
                                  clock=lambda: t["now"]) is None
    assert not r.exists()


def test_inject_reload():
    html = "<html><head></head><body></body></html>"
    out = refit.inject_reload(html, True)
    assert 'id="styx-refit"' in out and "4002" in out and "styx-resizing" in out and refit.MARKER in out
    assert "socket_worker" in out and "window.WebSocket=S" in out and out.index("styx-refit") < out.index("</head>")
    assert "Resizing" in refit.HOLD_HTML
    assert refit.inject_reload(html, False) == html
    assert refit.inject_reload("<p>no head</p>", True) == "<p>no head</p>"


def test_differs():
    assert refit.differs((2552, 1294), (1920, 1080)) is True
    assert refit.differs((2560, 1300), (2552, 1294)) is False
    assert refit.differs((2552, 1294), None) is True


def test_hold_page_waits_instead_of_blind_reload():
    assert "styxWait()" in refit.HOLD_HTML and "X-Styx-Hold" in refit.HOLD_HTML
    assert "location.reload()},500" not in refit.HOLD_HTML


def test_wait_for_request_stops_early(tmp_path):
    t = {"now": 0.0}
    assert refit.wait_for_request(tmp_path / "r", 30, sleep=lambda s: t.update(now=t["now"] + s),
                                  clock=lambda: t["now"], stop=lambda: True) is None
    assert t["now"] == 0.0


def test_shim_reconnects_transparently():
    out = refit.inject_reload("<html><head></head><body></body></html>", True)
    assert "_resume" in out and "START_VIDEO" in out and "X-Styx-Hold" in out and "location.reload()" in out


def test_size_owner_first_viewer_wins_until_it_leaves():
    o = refit.SizeOwner()
    assert o.claim("a") and not o.claim("b") and o.claim("a")
    o.release("b")
    assert o.owner == "a"
    o.release("a")
    assert o.claim("b")
