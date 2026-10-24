#!/usr/bin/env python3
"""LAN-facing gateway: authenticated reverse proxy to loopback selkies.

Fronts selkies 2.x (which serves its own client and /api/*) with auth, idle enforcement and injected shims.
Basic auth on everything: Traefik injects the Authorization header for portal
users; direct LAN visits get a browser prompt.

Usage: venv/bin/python gateway.py <listen_port> <upstream_port>
Credentials via env: STYX_GW_USER / STYX_GW_PASSWORD (argv is world-readable).
"""
import asyncio
import base64
import hmac
import json
import os
import posixpath
import socket
import sys
import time
import uuid
from pathlib import Path

import aiohttp
import favicon
import refit
import seat_scale
import yarl
from aiohttp import web
from multidict import CIMultiDict
from viewers import Viewers, split_vid
from gateway_html import (  # noqa: F401  (re-exported for tests)
    CURSOR_HIDE_CSS,
    VIS_GRACE_MS,
    inject_cursor_hide,
    inject_idle_watchdog,
    inject_title,
    inject_favicon,
    is_activity,
    is_bare_motion,
)


# How long a session that already streamed may go frameless, with the user
# still driving it, before the stream counts as wedged again. Covers the
# wlroots swapchain-exhaustion failure (screencopy holds every output buffer ->
# the compositor renders nothing and the engine emits no frames while still
# reporting "capture started") and any other mid-session stall. Must clear a
# normal input->frame round trip on a loaded host. ponytail: bump if a slow
# link ever trips it mid-session.
STALL_REARM_S = 2.0

# A viewer that lost its last socket keeps ownership this long: a refit closes
# every socket at once and the owner returns with the same styx_vid.
OWNER_GRACE_S = 5.0
REFIT_HOLD_S = 30.0     # no handoff this soon after a refit (clients are reconnecting)

# selkies keeps one controller and kills the previous one when another
# connects, so a stale tab on another machine that reconnects would kick the
# active session (and the kicked tab reconnecting kicks back). The gateway
# refuses a new controller tab with BUSY_CODE while another tab had input
# within the idle timeout (BUSY_HOLD_S when idle enforcement is off).
BUSY_CODE = refit.BUSY_CODE
BUSY_HOLD_S = 300.0
# A socket's first seconds are the client's connect burst (size, settings), not
# a person: a tab left open elsewhere reconnects on a loop and would otherwise
# renew its busy hold forever. The per-tab clock ignores input that early.
CONNECT_QUIET_S = 5.0
# a refit reconnect beats the standby promotion; land it on the new selkies
REFIT_WAIT_S = 5.0
REFIT_POLL_S = 0.02
# pings keep a hidden tab's quiet socket alive through proxies that drop idle connections (~139 s)
WS_HEARTBEAT_S = 30.0
STALL_LOG_S = 1.0       # client silent this long while video is on -> log it


class StallClock:
    """Per client socket: gap since its previous message while video is active."""
    def __init__(self, now: float):
        self.last = now
        self.video = False

    def tick(self, data, now: float):
        gap = now - self.last
        hit = gap if self.video and gap > STALL_LOG_S else None
        self.last = now
        if data == "START_VIDEO":
            self.video = True
        elif data == "STOP_VIDEO":
            self.video = False
        return hit


def log(msg: str) -> None:
    print(f"{time.strftime('%Y-%m-%d %H:%M:%S')} gateway: {msg}", flush=True)

# Proxied downloads may run arbitrarily long: no total cap, only connect/idle.
PROXY_TIMEOUT = aiohttp.ClientTimeout(total=None, sock_connect=10)


def check_auth(header: str, user: str, password: str) -> bool:
    if not header or not header.startswith("Basic "):
        return False
    try:
        got = base64.b64decode(header[6:], validate=True).decode()
    except Exception:
        return False
    expected = f"{user}:{password}"
    return hmac.compare_digest(got.encode(), expected.encode())


def create_app(user: str, password: str,
               upstream_port: int, files_dir: str = "",
               state_file: str = "", idle_timeout_s: int = 0,
               idle_lead_s: int = 60, idle_enabled: bool = False,
               seat_dir: str = "", icon_dir: str = "") -> web.Application:
    # The supervisor can promote a warm standby selkies on a refit: the live
    # port is then in <seat_dir>/selkies-port, re-read per request.
    port_file = os.path.join(seat_dir, "selkies-port") if seat_dir else ""

    def live_port() -> int:
        try:
            return int(open(port_file).read().strip())
        except (OSError, ValueError):
            return upstream_port

    def upstream() -> str:
        return f"http://127.0.0.1:{live_port()}"
    HOP = {"host", "connection", "keep-alive", "transfer-encoding", "upgrade",
           "authorization", "origin", "content-length", "accept-encoding"}

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
    # `last_frame` additionally times mid-session stalls: see mark_input.
    stream = {"got_frame": False, "starve_start": 0.0, "last_frame": 0.0}
    # GNOME seat refit (refit.py): rebuild at the browser size once resizing settles.
    size_file = os.path.join(seat_dir, "seat-size") if seat_dir else ""
    refit_file = os.path.join(seat_dir, "refit-request") if seat_dir else ""
    last_refit = {"ts": float("-inf")}
    scale_file = os.path.join(seat_dir, "seat-scale") if seat_dir else ""
    size_owner = refit.SizeOwner()
    viewers = Viewers()     # per styx_vid: sockets, last size/dpi, timers

    def publish_scale(rec):
        """Owner's HiDPI choice -> <install>/seat-scale (the seat helper applies it)."""
        if scale_file and rec.dpi is not None:
            want = seat_scale.scale_for_dpi(rec.dpi)
            if want != seat_scale.read_scale(scale_file):
                seat_scale.write_scale(scale_file, want)

    transports = {}     # client ws -> its TCP transport (abort = 1006, selkies 2.1 reconnects)

    def abort_for_refit(w):
        t = transports.get(w)
        if not w.closed and t is not None and not t.is_closing():
            t.abort()

    def fire_refit(rec):
        if rec.size is None or size_owner.owner != rec.vid:
            return                  # a stale timer of a previous owner
        target = refit.decide(rec.size, refit.read_size(size_file),
                              last_refit["ts"], time.time())
        if target is None or not any(not w.closed for w in rec.socks):
            return
        if isinstance(target, float):      # too soon: keep the size, retry later
            rec.timer = asyncio.get_running_loop().call_later(target, fire_refit, rec)
            return
        last_refit["ts"] = time.time()
        refit.request(refit_file, *target)
        # Every viewer's upstream socket dies with the old selkies: cut each
        # client socket so selkies 2.1 reconnects in place (it reloads on a clean close).
        for r in viewers.live():
            for w in list(r.socks):
                abort_for_refit(w)

    def set_owner(vid):
        """Ownership moves to `vid`: publish its scale, refit to its size."""
        prev, rec = size_owner.owner, viewers.by_vid.get(vid)
        if rec is None or prev == vid:
            return
        size_owner.owner = vid
        if prev in viewers.by_vid:
            old = viewers.by_vid[prev]
            old.timer and old.timer.cancel()
        publish_scale(rec)
        rec.timer and rec.timer.cancel()
        fire_refit(rec)

    def expire(vid):
        """Grace over for a viewer with no socket: forget it; hand the size to the newest."""
        rec = viewers.by_vid.get(vid)
        if rec is None or rec.socks:
            return
        if time.time() - last_refit["ts"] < REFIT_HOLD_S:   # refit reconnect still in flight
            rec.gone = asyncio.get_running_loop().call_later(OWNER_GRACE_S, expire, vid)
            return
        viewers.drop(vid)
        if size_owner.owner == vid:
            size_owner.release(vid)
            nxt = viewers.newest()
            if nxt is not None:
                set_owner(nxt)

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
        """First video frame of this session -> viewer no longer starving.
        Every frame also stamps `last_frame`, the mid-session stall clock."""
        stream["last_frame"] = time.time()
        if not stream["got_frame"]:
            stream["got_frame"] = True
            _write_state()   # publish promptly; disarms the supervisor watchdog

    def mark_input(data, rec=None):
        """Mark real client input activity; throttle state-file writes. Keepalive
        chatter (pong) is ignored so the idle clock actually advances. `rec`
        carries the per-tab clock (idle close, busy hold); the global one only
        feeds the occupancy state file."""
        if not is_activity(data):
            return
        now = time.time()
        last_input["ts"] = now
        if rec is not None:
            rec.last_input = now
        # Frames stopped while the user is still driving the seat -> the stream
        # is wedged, not idle. Re-arm the starvation flag so the supervisor
        # restarts the engine. Input is the discriminator: a healthy static
        # screen sends no frames either, but nobody is asking it to.
        if (stream["got_frame"] and now - stream["last_frame"] > STALL_REARM_S
                and not is_bare_motion(data)):
            stream["got_frame"] = False
            stream["starve_start"] = now
            last_input["flushed"] = now
            _write_state()
            return
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
        qs, vid = split_vid(request.rel_url.raw_query_string, f"ws{uuid.uuid4().hex}")
        if request.headers.get("Upgrade", "").lower() != "websocket":
            # 2.0 client probes api/websockets over plain HTTP (409 = mode flip)
            return await forward(request, "/api/websockets" + (f"?{qs}" if qs else ""))
        t0 = time.monotonic()
        while refit_file and refit.pending(refit_file) and time.monotonic() - t0 < REFIT_WAIT_S:
            await asyncio.sleep(REFIT_POLL_S)
        shared = "role=viewer" in qs.split("&")
        peer = (request.headers.get("CF-Connecting-IP")      # real client via the tunnel
                or request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
                or request.remote)
        hold = idle_timeout_s if idle_enabled and idle_timeout_s > 0 else BUSY_HOLD_S
        if not shared and viewers.busy(vid, time.time(), hold):
            # Refuse before upstream connects: selkies would kill the active one.
            ws_server = web.WebSocketResponse()
            await ws_server.prepare(request)
            log(f"ws reject vid={vid[:8]} from={peer}: seat in use by another tab")
            await ws_server.close(code=BUSY_CODE, message=b"superseded: in use on another device")
            return ws_server
        async with aiohttp.ClientSession() as session:
            try:
                ws_client = await session.ws_connect(
                    f"ws://127.0.0.1:{live_port()}/api/websockets"
                    + (f"?{qs}" if qs else ""),
                    max_msg_size=0)
            except aiohttp.ClientError:
                return web.Response(status=502, text="stream backend unavailable")
            conns["n"] += 1
            now = opened = time.time()
            last_input["ts"] = now  # fresh session: reset idle counter
            if conns["n"] == 1:     # first viewer: arm the stream-start watchdog
                stream["got_frame"] = False
                stream["starve_start"] = now
                stream["last_frame"] = now
            _write_state()
            rec = None
            try:
                # compress=False: frames are H264 — permessage-deflate would
                # re-DEFLATE every frame in Python for no gain.
                ws_server = web.WebSocketResponse(max_msg_size=0, compress=False,
                                               heartbeat=WS_HEARTBEAT_S)
                await ws_server.prepare(request)
                transports[ws_server] = request.transport
                stall = StallClock(time.time())

                async def pump(src, dst, on_activity=None, on_binary=None):
                    async for msg in src:
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            if on_activity and on_activity(msg.data):
                                continue        # swallowed (refit-bound resize)
                            await dst.send_str(msg.data)
                        elif msg.type == aiohttp.WSMsgType.BINARY:
                            if on_activity:
                                on_activity(msg.data)
                            # 0x01 = pcmflux audio; it flows while video is
                            # dead, so it must not count as a frame.
                            if on_binary and msg.data[:1] != b"\x01":
                                on_binary()
                            await dst.send_bytes(msg.data)
                        else:
                            break
                    await dst.close()

                async def idle_closer():
                    """Authoritative idle timeout: close the client socket once
                    this tab sent no input for idle_timeout_s. Ends the pumps."""
                    if not (idle_enabled and idle_timeout_s > 0):
                        return
                    while not ws_server.closed:
                        idle = time.time() - max(opened, rec.last_input)
                        if idle >= idle_timeout_s:
                            log(f"ws idle-close vid={vid[:8]} after {int(idle)}s")
                            await ws_server.close(
                                code=4001, message=b"idle timeout")   # 2.1: 4001 is final, no reconnect
                            return
                        await asyncio.sleep(min(1.0, idle_timeout_s))

                # client->upstream: input (idle tracking). upstream->client:
                # video frames are BINARY -> mark_frame disarms the watchdog.
                rec = viewers.connect(vid, ws_server)
                rec.vid = vid

                def on_client(data) -> bool:
                    """Input tracking + settle-then-refit. Every seat `r,` is
                    swallowed: selkies cannot resize a GNOME host (it would only
                    restart capture / log "resize refused"); the agent refits
                    instead, and only for the size owner."""
                    gap = stall.tick(data, time.time())
                    if gap is not None:
                        log(f"ws stall vid={vid[:8]} from={peer}: client silent {gap:.1f}s")
                    quiet = time.time() - opened < CONNECT_QUIET_S
                    mark_input(data, None if quiet else rec)
                    if not seat_dir or not isinstance(data, str):
                        return False
                    if data.startswith("SETTINGS,"):
                        try:
                            rec.dpi = float(json.loads(data[9:]).get("scaling_dpi"))
                        except (ValueError, TypeError, AttributeError):
                            return False
                        if size_owner.owner == vid:
                            publish_scale(rec)
                        return False
                    req = refit.parse_resize(data)
                    if not req:
                        return False
                    rec.size = req
                    if size_owner.claim(vid):
                        rec.timer and rec.timer.cancel()
                        rec.timer = asyncio.get_running_loop().call_later(refit.SETTLE_S, fire_refit, rec)
                    return True

                # selkies keeps one controller and kills the previous one, so a
                # controller owns the size at once. Shared (`role=viewer`) sockets
                # never send `r,` and never own.
                rec.shared = shared
                log(f"ws open vid={vid[:8]} role={'viewer' if shared else 'controller'} "
                    f"from={peer} (n={conns['n']})")
                if seat_dir and not rec.shared:
                    if size_owner.owner and size_owner.owner != vid:
                        set_owner(vid)
                    else:
                        size_owner.claim(vid)

                await asyncio.gather(pump(ws_server, ws_client, on_activity=on_client),
                                     pump(ws_client, ws_server, on_binary=mark_frame),
                                     idle_closer(),
                                     return_exceptions=True)
            finally:
                conns["n"] -= 1
                if rec:
                    log(f"ws close vid={vid[:8]} code={ws_server.close_code} "
                        f"after {int(time.time() - opened)}s (n={conns['n']})")
                transports.pop(ws_server, None)
                if rec and viewers.disconnect(vid, ws_server):
                    rec.timer and rec.timer.cancel()
                    # Not released at once: a refit reconnect brings the same vid back.
                    rec.gone = asyncio.get_running_loop().call_later(OWNER_GRACE_S, expire, vid)
                _write_state()
                await ws_client.close()
        return ws_server

    async def index(_request):
        hold = web.Response(text=refit.HOLD_HTML, content_type="text/html",
                            headers={"Cache-Control": "no-store", "X-Styx-Hold": "1"})
        if refit_file and refit.pending(refit_file):
            return hold
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as s, \
                    s.get(upstream() + "/", allow_redirects=False) as r:
                if r.status != 200:
                    hdr = {"Location": r.headers["Location"]} if "Location" in r.headers else {}
                    return web.Response(status=r.status, body=await r.read(), headers=hdr)
                html = await r.text()
        except aiohttp.ClientError:
            if seat_dir:            # GNOME seat: selkies restarting after a refit
                return hold
            return web.Response(status=502, text="stream backend unavailable")
        except asyncio.TimeoutError:
            return web.Response(status=504, text="stream backend timed out")
        html = inject_title(html, socket.gethostname())
        icon = favicon.read(Path(icon_dir)) if icon_dir else None
        if icon:
            html = inject_favicon(html, icon[2])
        html = inject_idle_watchdog(html, idle_timeout_s, idle_lead_s, idle_enabled)
        html = inject_cursor_hide(html, bool(seat_dir))
        html = refit.inject_reload(html, bool(seat_dir))
        return web.Response(text=html, content_type="text/html")

    async def styx_favicon(_request):
        icon = favicon.read(Path(icon_dir)) if icon_dir else None
        if not icon:
            return web.Response(status=404)
        return web.Response(body=icon[0], content_type=icon[1], headers={
            "Cache-Control": "no-cache", "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy":
                "default-src 'none'; style-src 'unsafe-inline'; sandbox"})

    def _relative_location(request, loc):
        """Absolute-path redirects would escape a /w/<slug> prefix; make them
        relative to the request path."""
        if not loc.startswith("/") or loc.startswith("//"):
            return loc
        path, sep, query = loc.partition("?")
        rel = posixpath.relpath(path, posixpath.dirname(request.path) or "/")
        if path.endswith("/") and not rel.endswith("/"):
            rel += "/"
        return rel + sep + query

    async def forward(request, raw_path_qs):
        """Stream request to selkies and its response back, as-is."""
        headers = CIMultiDict()
        headers.extend((k, v) for k, v in request.headers.items()
                       if k.lower() not in HOP)
        body = await request.read() if request.body_exists else None
        url = yarl.URL(upstream() + raw_path_qs, encoded=True)
        resp = None
        try:
            async with aiohttp.ClientSession(
                    auto_decompress=False, timeout=PROXY_TIMEOUT) as s, s.request(
                    request.method, url, headers=headers, data=body,
                    allow_redirects=False) as r:
                out = CIMultiDict()
                out.extend((k, v) for k, v in r.headers.items()
                           if k.lower() not in HOP)
                if "Location" in out:
                    out["Location"] = _relative_location(request, out["Location"])
                resp = web.StreamResponse(status=r.status, headers=out)
                await resp.prepare(request)
                async for chunk in r.content.iter_chunked(64 * 1024):
                    await resp.write(chunk)
                await resp.write_eof()
                return resp
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            if resp is not None and resp.prepared:
                # headers already sent: drop the connection, never append a 2nd response
                resp.force_close()
                if request.transport:
                    request.transport.close()
                raise
            if isinstance(e, asyncio.TimeoutError):
                return web.Response(status=504, text="stream backend timed out")
            return web.Response(status=502, text="stream backend unavailable")

    async def http_proxy(request):
        """Everything else (client assets, /api/* REST) goes to selkies as-is."""
        return await forward(request, request.rel_url.raw_path_qs)

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

    app = web.Application(middlewares=[auth_mw], client_max_size=0)
    for path in ("/api/websockets", "/websockets", "/websocket"):
        app.router.add_get(path, ws_proxy)
    app.router.add_get("/", index)
    app.router.add_get("/styx-favicon", styx_favicon)
    if files_dir and os.path.isdir(files_dir):
        app.router.add_get("/files", files)
        app.router.add_get("/files/{path:.*}", files)
    app.router.add_route("*", "/{tail:.*}", http_proxy)
    return app


def main() -> None:
    listen_port, upstream_port = int(sys.argv[1]), int(sys.argv[2])
    user = os.environ["STYX_GW_USER"]
    password = os.environ["STYX_GW_PASSWORD"]
    files_dir = os.path.expanduser(
        os.environ.get("STYX_FILES_DIR", "~/Downloads"))
    state_file = os.environ.get("STYX_GW_STATE", "")
    idle_timeout_s = int(os.environ.get("STYX_GW_IDLE_TIMEOUT_S", "0") or "0")
    idle_lead_s = int(os.environ.get("STYX_GW_IDLE_WARN_S", "60") or "60")
    idle_enabled = os.environ.get("STYX_GW_IDLE_ENABLED", "") == "1"
    seat_dir = os.environ.get("STYX_GW_SEAT_DIR", "")
    icon_dir = os.environ.get("STYX_GW_ICON_DIR", "")
    web.run_app(create_app(user, password, upstream_port, files_dir,
                           state_file=state_file, idle_timeout_s=idle_timeout_s,
                           idle_lead_s=idle_lead_s, idle_enabled=idle_enabled,
                           seat_dir=seat_dir, icon_dir=icon_dir),
                host="0.0.0.0", port=listen_port)


if __name__ == "__main__":
    main()
