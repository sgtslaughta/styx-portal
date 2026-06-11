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
               upstream_port: int) -> web.Application:
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

    app = web.Application(middlewares=[auth_mw])
    app.router.add_get("/websocket", ws_proxy)
    app.router.add_get("/", index)
    app.router.add_static("/", web_dir)
    return app


def main() -> None:
    web_dir, listen_port, upstream_port = (
        sys.argv[1], int(sys.argv[2]), int(sys.argv[3]))
    user = os.environ["STYX_GW_USER"]
    password = os.environ["STYX_GW_PASSWORD"]
    web.run_app(create_app(web_dir, user, password, upstream_port),
                host="0.0.0.0", port=listen_port)


if __name__ == "__main__":
    main()
