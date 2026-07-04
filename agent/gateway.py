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
import json
import os
import socket
import sys
import time

import aiohttp
from aiohttp import web


def inject_title(html: str, hostname: str) -> str:
    """Inject a <head> shim that (1) pins the tab title to the workstation
    hostname and (2) forces the stream to stay live regardless of tab visibility.

    Title: the selkies client hardcodes `document.title="Selkies"` at init (and
    re-sets it on reconnect), so a one-shot title loses the race. ponytail: a 1s
    poll re-asserts it; drop the interval if upstream stops clobbering it.

    Visibility: the selkies client sends STOP_VIDEO whenever `document.hidden` is
    true and only resumes on a `visibilitychange` back to visible. Embedded in
    the portal iframe, `document.hidden` follows the parent TAB — so backgrounding
    the portal (or (re)connecting while it's already hidden, which fires no
    visibilitychange) leaves the seat stuck on a black "Waiting for stream". A
    portal workstation should always stream, so override `hidden`/`visibilityState`
    to report visible. Runs in <head>, before the deferred selkies bundle reads
    them. The server-side idle timeout still releases a genuinely-idle seat.

    Hostname goes through json.dumps -> safe JS string literal (XSS-safe)."""
    script = ("<script>(function(){var t=%s;document.title=t;"
              "setInterval(function(){if(document.title!==t)document.title=t;},1000);"
              "try{Object.defineProperty(document,'hidden',"
              "{configurable:true,get:function(){return false;}});"
              "Object.defineProperty(document,'visibilityState',"
              "{configurable:true,get:function(){return 'visible';}});}catch(e){}"
              "})();</script>") % json.dumps(hostname)
    if "</head>" in html:
        return html.replace("</head>", script + "</head>", 1)
    return script + html


def inject_idle_watchdog(html: str, timeout_s: int, lead_s: int,
                         enabled: bool) -> str:
    """Inject the inactivity overlay: a countdown warning at T-lead and a
    terminal 'timed out — Reconnect' screen at T. UX only — the gateway is the
    authority and closes the socket server-side (see create_app), so this needs
    no access to Selkies' WebSocket. The local clock and the server clock both
    start from the same last input, so they fire together without coordination;
    the gateway backstops a throttled/frozen background tab.

    No-op when disabled or timeout_s <= 0 (never times out). `lead_s` is clamped
    below timeout_s/2 so the warning can't outlive the timeout. Values are ints
    -> safe to interpolate into the script."""
    if not enabled or timeout_s <= 0:
        return html
    lead = max(1, min(int(lead_s), int(timeout_s) // 2))
    script = ("<script>(function(){"
              "var T=%d,LEAD=%d,last=Date.now(),ov=null,dead=false;"
              "function mk(){var d=document.createElement('div');"
              "d.style.cssText='position:fixed;inset:0;z-index:2147483647;"
              "display:flex;align-items:center;justify-content:center;"
              "flex-direction:column;font:600 20px system-ui,sans-serif;"
              "color:#e6e9ef;background:rgba(17,20,28,.85);text-align:center';"
              "document.body.appendChild(d);return d;}"
              "function hide(){if(ov&&!dead){ov.remove();ov=null;}}"
              "function reset(){last=Date.now();hide();}"
              "['mousemove','mousedown','keydown','wheel','touchstart']"
              ".forEach(function(e){addEventListener(e,reset,"
              "{capture:true,passive:true});});"
              "setInterval(function(){if(dead)return;"
              "var idle=(Date.now()-last)/1000;"
              "if(idle>=T){dead=true;if(!ov)ov=mk();"
              "ov.innerHTML='<div>Session timed out due to inactivity</div>"
              "<button id=\"styx-rc\" style=\"margin-top:16px;padding:8px 20px;"
              "font:inherit;cursor:pointer;border-radius:8px;border:0;"
              "background:#2b3650;color:#fff\">Reconnect</button>';"
              "document.getElementById('styx-rc').onclick=function(){"
              "location.reload();};}"
              "else if(idle>=T-LEAD){if(!ov)ov=mk();"
              "ov.textContent='Disconnecting in '+Math.ceil(T-idle)+"
              "'s due to inactivity — move to stay';}"
              "else hide();},1000);})();</script>") % (int(timeout_s), lead)
    if "</head>" in html:
        return html.replace("</head>", script + "</head>", 1)
    return script + html


def is_activity(data) -> bool:
    """Whether a client->server message counts as user activity for idle timing.

    Selkies answers the server's periodic (~5s) ping with 'pong,<ts>'. Counting
    that keepalive resets the idle clock every few seconds, so the seat never
    times out — the reason workstation idle appeared not to work at all. Exclude
    it; genuine input (mouse/key/scroll/touch, clipboard, resolution) still counts.
    ponytail: add other prefixes here if a new non-input keepalive turns up."""
    return not (isinstance(data, str) and data.startswith("pong,"))


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
               upstream_port: int, files_dir: str = "",
               state_file: str = "", idle_timeout_s: int = 0,
               idle_lead_s: int = 60, idle_enabled: bool = False) -> web.Application:
    # Live stream-websocket count, mirrored to a state file the supervisor
    # reads each heartbeat — the portal uses it for occupancy ("in use by").
    conns = {"n": 0}
    # Track last client->server input timestamp (seconds since epoch).
    # Reset on each connection; throttle disk writes.
    last_input = {"ts": time.time(), "flushed": 0.0}
    # Stream-start liveness: a client can connect (its ws is proxied fine) yet
    # receive no video — upstream selkies left in STOP_VIDEO after the previous
    # tab closed, so the new tab's START_VIDEO never restarts capture ("Waiting
    # for stream" black screen). `got_frame` flips true on the first video
    # (binary) frame of a viewing session; until then the viewer is "starving"
    # and the supervisor restarts the engine. Cleared per session, so a healthy
    # but static screen (which stops sending frames) is never mistaken for stuck.
    stream = {"got_frame": False, "starve_start": 0.0}

    def _write_state():
        if not state_file:
            return
        try:
            tmp = state_file + ".tmp"
            with open(tmp, "w") as f:
                json.dump({"active_connections": conns["n"],
                           "last_input_ts": last_input["ts"],
                           "stream_starving": conns["n"] > 0
                           and not stream["got_frame"],
                           "starving_since": stream["starve_start"],
                           "ts": time.time()}, f)
            os.replace(tmp, state_file)
        except OSError:
            pass  # occupancy is advisory; never break the stream over it

    def mark_frame():
        """First video frame of this session -> viewer no longer starving."""
        if not stream["got_frame"]:
            stream["got_frame"] = True
            _write_state()   # publish promptly; disarms the supervisor watchdog

    def mark_input(data):
        """Mark real client input activity; throttle state-file writes. Keepalive
        chatter (pong) is ignored so the idle clock actually advances."""
        if not is_activity(data):
            return
        now = time.time()
        last_input["ts"] = now
        if now - last_input["flushed"] >= 5:   # throttle disk writes
            last_input["flushed"] = now
            _write_state()

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
            conns["n"] += 1
            now = time.time()
            last_input["ts"] = now  # fresh session: reset idle counter
            if conns["n"] == 1:     # first viewer: arm the stream-start watchdog
                stream["got_frame"] = False
                stream["starve_start"] = now
            _write_state()
            try:
                ws_server = web.WebSocketResponse(max_msg_size=0)
                await ws_server.prepare(request)

                async def pump(src, dst, on_activity=None, on_binary=None):
                    async for msg in src:
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            if on_activity:
                                on_activity(msg.data)
                            await dst.send_str(msg.data)
                        elif msg.type == aiohttp.WSMsgType.BINARY:
                            if on_activity:
                                on_activity(msg.data)
                            if on_binary:
                                on_binary()
                            await dst.send_bytes(msg.data)
                        else:
                            break
                    await dst.close()

                async def idle_closer():
                    """Authoritative idle timeout: close the client socket once
                    no input has arrived for idle_timeout_s. Ends the pumps."""
                    if not (idle_enabled and idle_timeout_s > 0):
                        return
                    while not ws_server.closed:
                        idle = time.time() - last_input["ts"]
                        if idle >= idle_timeout_s:
                            await ws_server.close(
                                code=4001, message=b"idle timeout")
                            return
                        await asyncio.sleep(min(1.0, idle_timeout_s))

                # client->upstream: input (idle tracking). upstream->client:
                # video frames are BINARY -> mark_frame disarms the watchdog.
                await asyncio.gather(pump(ws_server, ws_client, on_activity=mark_input),
                                     pump(ws_client, ws_server, on_binary=mark_frame),
                                     idle_closer(),
                                     return_exceptions=True)
            finally:
                conns["n"] -= 1
                _write_state()
                await ws_client.close()
        return ws_server

    async def index(_request):
        path = os.path.join(web_dir, "index.html")
        try:
            with open(path, encoding="utf-8") as f:
                html = inject_title(f.read(), socket.gethostname())
                html = inject_idle_watchdog(html, idle_timeout_s, idle_lead_s,
                                            idle_enabled)
        except OSError:
            return web.FileResponse(path)  # let aiohttp 404/handle it
        return web.Response(text=html, content_type="text/html")

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

    _write_state()   # reset any stale count from a previous gateway run

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
    state_file = os.environ.get("STYX_GW_STATE", "")
    idle_timeout_s = int(os.environ.get("STYX_GW_IDLE_TIMEOUT_S", "0") or "0")
    idle_lead_s = int(os.environ.get("STYX_GW_IDLE_WARN_S", "60") or "60")
    idle_enabled = os.environ.get("STYX_GW_IDLE_ENABLED", "") == "1"
    web.run_app(create_app(web_dir, user, password, upstream_port, files_dir,
                           state_file=state_file, idle_timeout_s=idle_timeout_s,
                           idle_lead_s=idle_lead_s, idle_enabled=idle_enabled),
                host="0.0.0.0", port=listen_port)


if __name__ == "__main__":
    main()
