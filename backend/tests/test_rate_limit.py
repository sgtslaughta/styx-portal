from app.middleware.rate_limit import SlidingWindow, client_ip_from_headers, is_strict_auth


def test_strict_only_for_credential_posts():
    # credential-submitting POSTs are strict
    assert is_strict_auth("POST", "/api/auth/login") is True
    assert is_strict_auth("POST", "/api/auth/accept-invite") is True
    assert is_strict_auth("POST", "/api/auth/setup") is True


def test_login_page_gets_are_not_strict():
    # routes the login page polls must NOT be in the brute-force bucket
    assert is_strict_auth("GET", "/api/auth/setup-required") is False
    assert is_strict_auth("GET", "/api/auth/me") is False
    assert is_strict_auth("GET", "/api/auth/oauth/providers") is False
    assert is_strict_auth("POST", "/api/auth/refresh") is False
    assert is_strict_auth("POST", "/api/auth/logout") is False


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


def test_ban_check_is_exempt():
    from app.middleware.rate_limit import is_rate_limit_exempt
    assert is_rate_limit_exempt("/api/auth/ban-check") is True
    assert is_rate_limit_exempt("/api/auth/login") is False


def test_middleware_reads_live_spec():
    from app.middleware.rate_limit import RateLimitMiddleware
    mw = RateLimitMiddleware(app=None)
    w1 = mw._window_for("3/60")
    assert w1.limit == 3 and w1.window == 60
    assert mw._window_for("3/60") is w1
    assert mw._window_for("9/60").limit == 9
