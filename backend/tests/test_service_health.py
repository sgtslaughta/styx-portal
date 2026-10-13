import asyncio
import time

import httpx
import pytest
from sqlmodel import select

from app.models import ProxiedService
from app.services.service_health import check_url, health_loop, run_health_pass


@pytest.mark.asyncio
async def test_health_pass_updates_status(session):
    a = ProxiedService(slug="a", name="A", upstream_url="http://10.0.0.1", health_path="/ping")
    b = ProxiedService(slug="b", name="B", upstream_url="https://10.0.0.2", health_path="/x",
                       verify_tls=False)
    c = ProxiedService(slug="c", name="C", upstream_url="http://10.0.0.3")   # no health_path
    d = ProxiedService(slug="d", name="D", upstream_url="http://10.0.0.4", health_path="/",
                       enabled=False)
    for s in (a, b, c, d):
        session.add(s)
    await session.commit()
    seen = []

    async def fake(url, verify):
        seen.append((url, verify))
        return "healthy" if url.startswith("http://10.0.0.1") else "unhealthy"

    n = await run_health_pass(session, checker=fake)
    assert n == 2
    assert seen == [("http://10.0.0.1/ping", True), ("https://10.0.0.2/x", False)]
    await session.refresh(a)
    await session.refresh(b)
    await session.refresh(c)
    assert (a.health_status, b.health_status, c.health_status) == ("healthy", "unhealthy", "unknown")
    assert a.health_checked_at is not None


@pytest.mark.asyncio
async def test_check_url_connection_error_is_unhealthy():
    assert await check_url("http://127.0.0.1:9", True) == "unhealthy"


@pytest.mark.asyncio
async def test_check_url_does_not_follow_redirects():
    calls = []

    def handler(req: httpx.Request) -> httpx.Response:
        calls.append(str(req.url))
        return httpx.Response(302, headers={"Location": "http://evil.example/steal"})

    r = await check_url("http://10.0.0.1/ping", True, transport=httpx.MockTransport(handler))
    assert r == "healthy"           # 3xx < 400, but never followed
    assert calls == ["http://10.0.0.1/ping"]


@pytest.mark.asyncio
async def test_check_url_5xx_unhealthy():
    t = httpx.MockTransport(lambda req: httpx.Response(503))
    assert await check_url("http://10.0.0.1/", True, transport=t) == "unhealthy"


@pytest.mark.asyncio
async def test_crashing_checker_does_not_affect_other_services(session):
    for slug in ("a", "b"):
        session.add(ProxiedService(slug=slug, name=slug, upstream_url=f"http://{slug}.lan",
                                   health_path="/h"))
    await session.commit()

    async def fake(url, verify):
        if "a.lan" in url:
            raise RuntimeError("boom")
        return "healthy"

    assert await run_health_pass(session, checker=fake) == 2
    rows = {s.slug: s.health_status for s in (await session.exec(
        select(ProxiedService))).all()}
    assert rows == {"a": "unhealthy", "b": "healthy"}


@pytest.mark.asyncio
async def test_checks_run_concurrently(session):
    for i in range(5):
        session.add(ProxiedService(slug=f"s{i}", name="s", upstream_url=f"http://h{i}.lan",
                                   health_path="/h"))
    await session.commit()

    async def slow(url, verify):
        await asyncio.sleep(0.3)
        return "healthy"

    t0 = time.monotonic()
    await run_health_pass(session, checker=slow)
    assert time.monotonic() - t0 < 1.0   # sequential would be 1.5s


@pytest.mark.asyncio
async def test_loop_survives_pass_exceptions_and_cancels_cleanly():
    passes = 0

    class Boom:
        async def __aenter__(self):
            nonlocal passes
            passes += 1
            raise RuntimeError("db down")

        async def __aexit__(self, *a):
            return False

    task = asyncio.create_task(health_loop(Boom, interval=0.01))
    await asyncio.sleep(0.15)
    assert passes >= 2 and not task.done()    # still alive after repeated failures
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


@pytest.mark.asyncio
async def test_lifespan_cancels_service_health_task(monkeypatch):
    import app.main as m
    started = asyncio.Event()
    state = {}

    async def fake_loop(factory, **kw):
        started.set()
        try:
            await asyncio.sleep(3600)
        except asyncio.CancelledError:
            state["cancelled"] = True
            raise

    monkeypatch.setattr("app.services.service_health.health_loop", fake_loop)
    task = asyncio.create_task(m._service_health_loop())
    await started.wait()
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    assert state["cancelled"]


@pytest.mark.asyncio
async def test_attached_docker_local_not_probed(session):
    """Backend is not on styx-services, so it cannot reach attached containers."""
    s = ProxiedService(slug="dl", name="DL", kind="docker-local", container="sonarr",
                       container_port=8989, health_path="/ping")
    fb = ProxiedService(slug="fb", name="FB", kind="docker-local", container="radarr",
                        container_port=7878, health_path="/ping",
                        upstream_fallback="http://host.docker.internal:7878")
    session.add(s)
    session.add(fb)
    await session.commit()
    seen = []

    async def fake(url, verify):
        seen.append(url)
        return "healthy"

    await run_health_pass(session, checker=fake)
    assert seen == ["http://host.docker.internal:7878/ping"]
    await session.refresh(s)
    assert s.health_status == "unknown"
