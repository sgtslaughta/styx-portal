import base64
from unittest.mock import MagicMock

import pytest

from app.models import ProxiedService
from app.services import service_favicon as sf

PAGE = "http://app:8080/sonarr/"
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 20
SVG = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1 1"><rect width="1" height="1"/></svg>'


def _html(*links):
    return "<html><head>" + "".join(links) + "</head></html>"


def test_candidates_order_svg_png_apple_other_ico():
    html = _html(
        '<link rel="shortcut icon" href="/x.gif">',
        '<link rel="apple-touch-icon" href="/apple.png">',
        '<link rel="icon" type="image/png" sizes="16x16" href="/16.png">',
        '<link rel="icon" type="image/png" sizes="64x64" href="/64.png">',
        '<link rel="icon" type="image/svg+xml" href="/i.svg">',
    )
    assert sf.candidates(html, PAGE) == [
        "http://app:8080/i.svg", "http://app:8080/64.png", "http://app:8080/16.png",
        "http://app:8080/apple.png", "http://app:8080/x.gif", "http://app:8080/favicon.ico"]


def test_any_size_counts_as_largest_and_svg_by_extension():
    html = _html('<link rel="icon" sizes="32x32" href="a.png">',
                 '<link rel="icon" sizes="any" href="b.png">',
                 '<link rel="icon" href="c.svg">')
    assert sf.candidates(html, PAGE)[:3] == [
        "http://app:8080/sonarr/c.svg", "http://app:8080/sonarr/b.png",
        "http://app:8080/sonarr/a.png"]


def test_no_links_falls_back_to_favicon_ico():
    assert sf.candidates("<html></html>", PAGE) == ["http://app:8080/favicon.ico"]


def test_same_origin_filter_drops_foreign_hosts_ports_schemes():
    html = _html('<link rel="icon" href="http://evil.test/a.png">',
                 '<link rel="icon" href="//evil.test/b.png">',
                 '<link rel="icon" href="http://app:9999/c.png">',
                 '<link rel="icon" href="https://app:8080/d.png">',
                 '<link rel="icon" href="ftp://app:8080/e.png">',
                 '<link rel="icon" href="/ok.png">')
    assert sf.candidates(html, PAGE) == ["http://app:8080/ok.png", "http://app:8080/favicon.ico"]


def test_data_href_kept_and_default_port_equals_explicit():
    html = _html('<link rel="icon" href="data:image/png;base64,AAAA">')
    assert sf.candidates(html, PAGE)[0] == "data:image/png;base64,AAAA"
    assert sf.same_origin("http://a/x", "http://a:80/y")
    assert not sf.same_origin("http://a/x", "http://a:81/y")


def test_non_icon_links_ignored():
    html = _html('<link rel="stylesheet" href="/s.css">', '<link rel="mask-icon" href="/m.svg">')
    assert sf.candidates(html, PAGE) == ["http://app:8080/favicon.ico"]


def _svc(**kw):
    d = dict(slug="sonarr", name="Sonarr", kind="docker-local", container="app",
             container_port=8080, mount_mode="path")
    d.update(kw)
    return ProxiedService(**d)


def _docker(pages: dict, moved: dict | None = None):
    """pages: url -> body. moved: url -> final url after (allowed) redirects."""
    d = MagicMock()

    def fetch(url, net, cap, with_url=False, **kw):
        final = (moved or {}).get(url, url)
        body = pages.get(final)
        return (None if body is None else (body, final)) if with_url else body
    d.probe_fetch.side_effect = fetch
    return d


@pytest.mark.asyncio
async def test_fetch_docker_resolves_icons_against_the_page_after_redirects():
    # Jellyfin: / -> 302 web/, whose icon links are relative to /web/
    html = _html('<link rel="icon" href="f5.png">').encode()
    d = _docker({"http://app:8080/web/": html, "http://app:8080/web/f5.png": PNG},
                moved={"http://app:8080/": "http://app:8080/web/"})
    out = await sf.fetch_favicon(_svc(mount_mode="cookie-root"), d)
    assert out and base64.b64decode(out.split(",")[1]) == PNG


@pytest.mark.asyncio
async def test_fetch_url_kind_resolves_icons_against_the_page_after_redirects():
    import httpx

    def handler(req: httpx.Request):
        if req.url.path == "/":
            return httpx.Response(302, headers={"location": "web/"})
        if req.url.path == "/web/":
            return httpx.Response(200, html=_html('<link rel="icon" href="f5.png">'))
        if req.url.path == "/web/f5.png":
            return httpx.Response(200, content=PNG)
        return httpx.Response(404)
    svc = _svc(kind="url", upstream_url="http://app.test:8080", container=None,
               mount_mode="cookie-root")
    out = await sf.fetch_favicon(svc, None, transport=httpx.MockTransport(handler))
    assert out and base64.b64decode(out.split(",")[1]) == PNG


@pytest.mark.asyncio
async def test_fetch_docker_picks_svg_and_stores_data_uri():
    html = _html('<link rel="icon" href="/i.svg">').encode()
    d = _docker({PAGE: html, "http://app:8080/i.svg": SVG})
    out = await sf.fetch_favicon(_svc(), d)
    assert out.startswith("data:image/svg+xml;base64,")
    urls = [c.args[0] for c in d.probe_fetch.call_args_list]
    assert urls[0] == PAGE
    assert d.probe_fetch.call_args_list[0].args[2] == sf.PAGE_CAP


@pytest.mark.asyncio
async def test_fetch_falls_through_invalid_candidate():
    html = _html('<link rel="icon" href="/bad.svg">', '<link rel="icon" href="/b.png">').encode()
    d = _docker({PAGE: html, "http://app:8080/bad.svg": b"<svg><script/></svg>",
                 "http://app:8080/b.png": PNG})
    out = await sf.fetch_favicon(_svc(), d)
    assert base64.b64decode(out.split(",")[1]) == PNG


@pytest.mark.asyncio
async def test_fetch_cookie_root_uses_base_and_none_when_nothing():
    d = _docker({})
    assert await sf.fetch_favicon(_svc(mount_mode="cookie-root"), d) is None
    assert d.probe_fetch.call_args_list[0].args[0] == "http://app:8080/"


@pytest.mark.asyncio
async def test_fetch_never_raises():
    d = MagicMock()
    d.probe_fetch.side_effect = RuntimeError("boom")
    assert await sf.fetch_favicon(_svc(), d) is None


@pytest.mark.asyncio
async def test_fetch_never_requests_foreign_origin():
    html = _html('<link rel="icon" href="http://evil.test/a.png">').encode()
    d = _docker({PAGE: html, "http://app:8080/favicon.ico": b"\x00\x00\x01\x00" + b"0" * 10})
    out = await sf.fetch_favicon(_svc(), d)
    assert out.startswith("data:image/x-icon")
    assert all("evil" not in c.args[0] for c in d.probe_fetch.call_args_list)


@pytest.mark.asyncio
async def test_fetch_url_kind_uses_httpx_same_origin_redirects_only():
    import httpx

    def handler(req: httpx.Request):
        if req.url.path == "/sonarr/":
            return httpx.Response(200, html=_html('<link rel="icon" href="/i.png">'))
        if req.url.path == "/i.png":
            return httpx.Response(200, content=PNG)
        return httpx.Response(404)
    svc = _svc(kind="url", upstream_url="http://app.test:8080", container=None)
    out = await sf.fetch_favicon(svc, None, transport=httpx.MockTransport(handler))
    assert base64.b64decode(out.split(",")[1]) == PNG

    def redirect(req):
        return httpx.Response(302, headers={"location": "http://evil.test/x"})
    assert await sf.fetch_favicon(svc, None, transport=httpx.MockTransport(redirect)) is None


@pytest.mark.asyncio
async def test_fetch_url_kind_caps_body():
    import httpx
    big = httpx.MockTransport(lambda r: httpx.Response(200, content=b"x" * 2_000_000))
    svc = _svc(kind="url", upstream_url="http://app.test:8080", container=None)
    assert await sf.fetch_favicon(svc, None, transport=big) is None


async def test_fetch_docker_local_on_k8s_uses_httpx(monkeypatch):
    import httpx
    monkeypatch.setenv("ROUTE_BACKEND", "k8s")
    seen = []

    def handler(req: httpx.Request):
        seen.append(str(req.url))
        if req.url.path == "/sonarr/":
            return httpx.Response(200, html=_html('<link rel="icon" href="i.png">'))
        if req.url.path == "/sonarr/i.png":
            return httpx.Response(200, content=PNG)
        return httpx.Response(404)
    d = MagicMock()
    out = await sf.fetch_favicon(_svc(container="app.media.svc"), d,
                                 transport=httpx.MockTransport(handler))
    assert out and base64.b64decode(out.split(",")[1]) == PNG
    assert seen and not d.probe_fetch.called
