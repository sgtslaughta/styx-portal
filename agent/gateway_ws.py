"""Plain WebSocket pass-through for selkies paths the gateway does not inspect.

WebRTC mode signals over /api/webrtc/signaling/: SDP and ICE as text, no video.
http_proxy cannot upgrade, so without this the client gets a 204 and retries
forever. No tracking here: gateway_webrtc.py wraps this for the signaling path.
"""
import asyncio

import aiohttp
import yarl
from aiohttp import web


def same_origin(request) -> bool:
    """Cross-site WebSocket hijacking guard: browsers replay cached Basic auth
    on a cross-site handshake, so a page elsewhere could drive the seat.
    No Origin = not a browser (curl, tests): allowed, auth still applies."""
    origin = request.headers.get("Origin")
    if origin is None:
        return True
    o, h = yarl.URL(origin), yarl.URL(f"//{request.host}")
    # Compare explicit ports only: `.authority` fills in the scheme's default
    # (https://x -> x:443) for the Origin but not for a bare Host header.
    return o.host == h.host and o.explicit_port == h.explicit_port


async def pump(src, dst):
    async for msg in src:
        if msg.type == aiohttp.WSMsgType.TEXT:
            await dst.send_str(msg.data)
        elif msg.type == aiohttp.WSMsgType.BINARY:
            await dst.send_bytes(msg.data)
        else:
            break
    await dst.close()


async def raw_ws_proxy(request, upstream_url: str):
    if request.headers.get("Upgrade", "").lower() != "websocket":
        return web.Response(status=426, text="websocket upgrade required")
    if not same_origin(request):
        return web.Response(status=403, text="forbidden origin")
    async with aiohttp.ClientSession() as session:
        try:
            up = await session.ws_connect(upstream_url, max_msg_size=0)
        except aiohttp.ClientError:
            return web.Response(status=502, text="stream backend unavailable")
        down = web.WebSocketResponse(max_msg_size=0)
        await down.prepare(request)
        await asyncio.gather(pump(down, up), pump(up, down), return_exceptions=True)
        await up.close()
        return down
