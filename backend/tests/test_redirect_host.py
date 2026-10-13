import pytest
from starlette.requests import Request

from app.routers import workstations as w


def req(**h):
    return Request({"type": "http", "headers": [(k.replace("_", "-").encode(), v.encode())
                                                 for k, v in h.items()]})


@pytest.fixture(autouse=True)
def cfg(monkeypatch):
    monkeypatch.setattr(w._settings, "DOMAIN", "styx.example.com")
    monkeypatch.setattr(w._settings, "SERVER_LAN_URL", "https://192.168.1.10:8443")


@pytest.mark.parametrize("hdrs,want", [
    ({"x_forwarded_host": "styx.example.com"}, "styx.example.com"),
    ({"x_forwarded_host": "styx.example.com:8443"}, "styx.example.com:8443"),
    ({"x_forwarded_host": "styx.example.com", "x_forwarded_port": "8443"}, "styx.example.com:8443"),
    ({"x_forwarded_host": "styx.example.com", "x_forwarded_port": "443"}, "styx.example.com"),
    ({"x_forwarded_host": "styx.example.com:443"}, "styx.example.com:443"),
    ({"x_forwarded_host": "styx.example.com:99999"}, "styx.example.com"),
    ({"x_forwarded_host": "styx.example.com", "x_forwarded_port": "abc"}, "styx.example.com"),
    ({"x_forwarded_host": "192.168.1.10:9000"}, "192.168.1.10:9000"),
    ({"x_forwarded_host": "10.0.0.5:18080"}, "10.0.0.5:18080"),
    ({"x_forwarded_host": "evil.com:8443"}, "styx.example.com"),
    ({"x_forwarded_host": "evil.com", "x_forwarded_port": "8443"}, "styx.example.com"),
    ({"x_forwarded_host": "styx.example.com.evil.com:8443"}, "styx.example.com"),
    ({}, "styx.example.com"),
])
def test_redirect_host(hdrs, want):
    assert w._redirect_host(req(**hdrs)) == want
