from app.middleware.rate_limit import SlidingWindow, client_ip_from_headers


def test_allows_under_limit():
    w = SlidingWindow(limit=3, window=60)
    assert all(w.allow("ip1", now=t) for t in (0, 1, 2))


def test_blocks_over_limit():
    w = SlidingWindow(limit=3, window=60)
    for t in (0, 1, 2):
        w.allow("ip1", now=t)
    assert w.allow("ip1", now=3) is False


def test_window_slides():
    w = SlidingWindow(limit=1, window=60)
    assert w.allow("ip1", now=0) is True
    assert w.allow("ip1", now=10) is False
    assert w.allow("ip1", now=61) is True


def test_keys_isolated():
    w = SlidingWindow(limit=1, window=60)
    assert w.allow("ip1", now=0) is True
    assert w.allow("ip2", now=0) is True


class _FakeReq:
    def __init__(self, headers, host="10.0.0.1"):
        self.headers = headers
        self.client = type("C", (), {"host": host})()


def test_prefers_cf_connecting_ip():
    req = _FakeReq({"cf-connecting-ip": "203.0.113.7", "x-forwarded-for": "198.51.100.1"})
    assert client_ip_from_headers(req) == "203.0.113.7"


def test_falls_back_to_first_xff():
    req = _FakeReq({"x-forwarded-for": "198.51.100.1, 10.0.0.5"})
    assert client_ip_from_headers(req) == "198.51.100.1"


def test_falls_back_to_client_host():
    req = _FakeReq({})
    assert client_ip_from_headers(req) == "10.0.0.1"
