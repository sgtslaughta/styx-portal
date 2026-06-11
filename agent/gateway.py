#!/usr/bin/env python3
"""LAN-facing gateway: dashboard static files + authenticated ws proxy.

Mirrors the upstream container's nginx layout (/ -> web dist, /websocket ->
loopback selkies) so the stock dashboard works unmodified. Basic auth on
everything: Traefik injects the Authorization header for portal users;
direct LAN visits get a browser prompt.

Usage: venv/bin/python gateway.py <web_dir> <listen_port> <upstream_port>
Credentials via env: STYX_GW_USER / STYX_GW_PASSWORD (argv is world-readable).
"""
import asyncio
import base64
import hmac
import os
import sys

import aiohttp
from aiohttp import web


def check_auth(header: str, user: str, password: str) -> bool:
    if not header or not header.startswith("Basic "):
        return False
    try:
        got = base64.b64decode(header[6:], validate=True).decode()
    except Exception:
        return False
    expected = f"{user}:{password}"
    return hmac.compare_digest(got.encode(), expected.encode())


def create_app(web_dir: str, user: str, password: str,
               upstream_port: int, files_dir: str = "") -> web.Application:
    @web.middleware
    async def auth_mw(request, handler):
        if not check_auth(request.headers.get("Authorization", ""), user, password):
            return web.Response(
                status=401, headers={"WWW-Authenticate": 'Basic realm="styx"'})
        return await handler(request)

    async def ws_proxy(request):
        async with aiohttp.ClientSession() as session:
            try:
                ws_client = await session.ws_connect(
                    f"ws://127.0.0.1:{upstream_port}{request.path}",
                    max_msg_size=0)
            except aiohttp.ClientError:
                return web.Response(status=502, text="stream backend unavailable")
            try:
                ws_server = web.WebSocketResponse(max_msg_size=0)
                await ws_server.prepare(request)

                async def pump(src, dst):
                    async for msg in src:
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            await dst.send_str(msg.data)
                        elif msg.type == aiohttp.WSMsgType.BINARY:
                            await dst.send_bytes(msg.data)
                        else:
                            break
                    await dst.close()

                await asyncio.gather(pump(ws_server, ws_client),
                                     pump(ws_client, ws_server),
                                     return_exceptions=True)
            finally:
                await ws_client.close()
        return ws_server

    async def index(_request):
        return web.FileResponse(os.path.join(web_dir, "index.html"))

    async def files(request):
        # Hand-rolled index: aiohttp's show_index emits ABSOLUTE hrefs
        # (/files/x), which escape the portal's /w/{sub} prefix and land on
        # the SPA (X-Frame-Options: DENY -> blocked iframe). Relative links
        # survive any prefix.
        import html as _html
        from pathlib import Path
        from urllib.parse import quote
        base = Path(files_dir).resolve()
        rel = request.match_info.get("path", "")
        target = (base / rel).resolve() if rel else base
        if not (target == base or target.is_relative_to(base)):
            raise web.HTTPForbidden()
        if target.is_file():
            return web.FileResponse(target)
        if not target.is_dir():
            raise web.HTTPNotFound()
        if not request.path.endswith("/"):
            # relative redirect keeps the reverse-proxy prefix intact
            raise web.HTTPMovedPermanently(quote(target.name) + "/")
        items = sorted(target.iterdir(),
                       key=lambda p: (not p.is_dir(), p.name.lower()))
        rows = "".join(
            f'<li><a href="{quote(p.name)}{"/" if p.is_dir() else ""}">'
            f'{_html.escape(p.name)}{"/" if p.is_dir() else ""}</a></li>'
            for p in items) or "<li><em>empty</em></li>"
        up = '<li><a href="../">../</a></li>' if target != base else ""
        body = (f"<!doctype html><meta charset='utf-8'><title>Files</title>"
                f"<style>body{{font:14px sans-serif;background:#fff;"
                f"color:#222;padding:1.5em}}li{{margin:.25em 0}}</style>"
                f"<h2>{_html.escape(str(target))}</h2><ul>{up}{rows}</ul>")
        return web.Response(text=body, content_type="text/html")

    app = web.Application(middlewares=[auth_mw])
    # The dashboard appends "websockets" to its base path (selkies-core.js);
    # upstream nginx also exposes /websocket. Route both.
    app.router.add_get("/websocket", ws_proxy)
    app.router.add_get("/websockets", ws_proxy)
    app.router.add_get("/", index)
    if files_dir and os.path.isdir(files_dir):
        # Dashboard's Files download popup opens <base>/files/.
        app.router.add_get("/files", files)
        app.router.add_get("/files/{path:.*}", files)
    app.router.add_static("/", web_dir)
    return app


def main() -> None:
    web_dir, listen_port, upstream_port = (
        sys.argv[1], int(sys.argv[2]), int(sys.argv[3]))
    user = os.environ["STYX_GW_USER"]
    password = os.environ["STYX_GW_PASSWORD"]
    files_dir = os.path.expanduser(
        os.environ.get("STYX_FILES_DIR", "~/Downloads"))
    web.run_app(create_app(web_dir, user, password, upstream_port, files_dir),
                host="0.0.0.0", port=listen_port)


if __name__ == "__main__":
    main()
