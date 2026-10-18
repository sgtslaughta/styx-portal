"""B2: outbound fetch denylist + DNS pinning."""
import httpx
import pytest

from app.services import service_health
from app.services.service_health import _forbidden_target, check_url


# ---- B2 ---------------------------------------------------------------
@pytest.mark.parametrize("url", [
    "http://127.0.0.1:8000/", "http://[::1]/", "http://0.0.0.0/", "http://localhost:8000/",
    "http://169.254.169.254/", "http://[::ffff:127.0.0.1]/",
])
async def test_denylist_loopback_and_metadata(url):
    assert await _forbidden_target(url)


async def test_denylist_internal_service_names(monkeypatch):
    async def fake_internal():
        import ipaddress
        return {ipaddress.ip_address("172.30.0.9")}
    monkeypatch.setattr(service_health, "_internal_addrs", fake_internal)
    assert await _forbidden_target("http://172.30.0.9:2375/")
    assert not await _forbidden_target("http://192.168.1.96:8080/")   # LAN stays allowed
    assert not await _forbidden_target("http://10.0.0.1/")


async def test_connect_pinned_to_checked_ip(monkeypatch):
    """The name is resolved once; the request goes to that IP (no 2nd lookup to rebind)."""
    calls = []

    async def fake_resolve(host):
        import ipaddress
        if host != "app.lan":
            return set()           # internal-name lookups
        calls.append(host)
        return {ipaddress.ip_address("192.168.1.50")}
    monkeypatch.setattr(service_health, "_resolve", fake_resolve)
    seen = []

    def handler(req: httpx.Request):
        seen.append((req.url.host, req.headers["host"], req.extensions.get("sni_hostname")))
        return httpx.Response(200)
    r = await check_url("https://app.lan/x", True, transport=httpx.MockTransport(handler))
    assert r == "healthy"
    assert seen == [("192.168.1.50", "app.lan", "app.lan")]
    assert calls == ["app.lan"]




async def test_dual_stack_pins_ipv4(monkeypatch):
    """F7: IPv6 inside IPv4-only docker would make health/favicons fail."""
    import ipaddress

    async def fake_resolve(host):
        if host != "dual.lan":
            return set()
        return {ipaddress.ip_address("1001:db8::1"), ipaddress.ip_address("192.168.1.60")}
    monkeypatch.setattr(service_health, "_resolve", fake_resolve)
    reason, pin = await service_health._checked("http://dual.lan/")
    assert pin == "192.168.1.60"
