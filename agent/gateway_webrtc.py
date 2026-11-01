"""WebRTC sessions in the gateway: signaling WS tracking, idle/max-age cut, beacons.

In WebRTC mode input and video ride a peer connection the gateway cannot see;
only the signaling WebSocket crosses it. So the injected page script (a) tags
that WebSocket with `styx_vid=<sid>` (a fresh id per page load, reused as the
session id) and (b) POSTs /styx/activity beacons on real input. A session with
no beacon for the idle timeout, or older than the hard cap, is cut: signaling
closed and selkies restarted (kill flag, see agent_procs) so the peer
connection, and any TURN relay traffic billed with it, really stops. Missing
beacons count as idle (a hidden or dead tab is cut: fail-safe)."""
import asyncio
import json
import time
import uuid
from pathlib import Path

import aiohttp
import refit
from aiohttp import web
from gateway_ws import pump, same_origin
from viewers import split_vid

FINAL_CODE = 4001       # idle/age cut; the client must not reconnect
GRACE_S = 60.0          # a session keeps its age/idle clocks across a signaling reconnect
HEARTBEAT_S = 30.0
MAX_RELAY = 10**13      # sanity bound on a client-reported counter
# Client-reported relay bytes are advisory (cost estimate only, never billing or
# access): a credit can't exceed elapsed time at this bitrate plus a little slack.
MAX_RELAY_BPS = 250e6
RELAY_SLACK_B = 10**7
KILL_SUFFIX = ".kill"   # <state file>.kill = "restart selkies now" (agent_procs polls it)


class Session:
    def __init__(self, sid: str, now: float):
        self.sid, self.opened, self.last_activity = sid, now, 0.0
        self.socks: set = set()
        self.relay_last = 0
        self.relay_ts = now
        self.dead = False
        self.gone_at = 0.0


class WebRTCGateway:
    def __init__(self, *, transport: str, idle_s: int, idle_enabled: bool, max_session_s: int,
                 hold_s: float, viewers, seat: bool, live_port, write_state, touch, kill_path,
                 attach, detach, submit_size, log=print, webrtc_off: bool = False):
        self.transport = transport if transport == "webrtc" else "websockets"
        self.idle_s = idle_s if idle_enabled and idle_s > 0 else 0
        self.max_s, self.hold_s = max_session_s, hold_s
        self.sessions: dict[str, Session] = {}
        self.turn_bytes = 0
        self.viewers, self.seat = viewers, seat
        self.live_port, self.write_state, self.touch, self.kill_path = live_port, write_state, touch, kill_path
        self.attach, self.detach, self.submit_size, self.log = attach, detach, submit_size, log
        self.gamemode = None
        self.webrtc_off = webrtc_off   # TURN budget reached: no WebRTC at all

    @property
    def n(self) -> int:
        """Live signaling sockets (added to active_connections)."""
        return sum(len(s.socks) for s in self.sessions.values())

    def state(self) -> dict:
        return {"turn_bytes_total": self.turn_bytes, "transport": self.transport}

    def install(self, app) -> None:
        app.router.add_get("/api/webrtc/signaling/", self.signaling)
        app.router.add_post("/styx/activity", self.activity)
        app.router.add_post("/styx/refit", self.refit)

    # -- session bookkeeping (pure) ------------------------------------------
    def expired(self, s: Session, now: float):
        if self.idle_s and now - max(s.opened, s.last_activity) >= self.idle_s:
            return "idle"
        if self.max_s > 0 and now - s.opened >= self.max_s:
            return "max-session"
        return None

    def _purge(self, now: float) -> None:
        for sid, s in list(self.sessions.items()):
            if not s.socks and now - s.gone_at > GRACE_S:
                del self.sessions[sid]

    def busy(self, sid: str, now: float) -> bool:
        return self.viewers.busy(sid, now, self.hold_s)

    def credit(self, s: Session, relay: int, now: float | None = None) -> None:
        """`relay` is cumulative per sid (monotonic page-side): count positive
        deltas, each capped at what MAX_RELAY_BPS could carry since the last one."""
        if relay > s.relay_last:
            now = time.time() if now is None else now
            cap = max(0.0, now - s.relay_ts) * MAX_RELAY_BPS / 8 + RELAY_SLACK_B
            self.turn_bytes += int(min(relay - s.relay_last, cap))
            s.relay_last, s.relay_ts = relay, now

    def kill(self, why: str) -> None:
        """Ask the supervisor to restart selkies (drops the peer connection)."""
        if self.kill_path:
            try:
                Path(self.kill_path).write_text(why)
            except OSError:
                pass

    # -- HTTP beacons --------------------------------------------------------
    @staticmethod
    async def _body(request) -> dict | None:
        if not same_origin(request):
            return None
        try:
            d = json.loads(await request.content.read(4096))
        except ValueError:
            return {}
        return d if isinstance(d, dict) else {}

    async def activity(self, request):
        d = await self._body(request)
        if d is None:
            return web.Response(status=403, text="forbidden origin")
        s = self.sessions.get(d.get("sid")) if isinstance(d.get("sid"), str) else None
        if s is None or s.dead or not s.socks:
            return web.Response(status=204)
        if d.get("active", True) is not False:
            now = time.time()
            s.last_activity = now
            rec = self.viewers.by_vid.get(s.sid)
            if rec:
                rec.last_input = now
            self.touch(now)
        r = d.get("relay_bytes")
        if isinstance(r, int) and not isinstance(r, bool) and 0 <= r <= MAX_RELAY:
            self.credit(s, r)
        self.write_state()
        return web.Response(status=204)

    async def refit(self, request):
        """Browser size -> the size-owner refit path ("r," never reaches the gateway)."""
        d = await self._body(request)
        if d is None:
            return web.Response(status=403, text="forbidden origin")
        try:
            dpr = float(d.get("dpr", 1))
            req = (round(float(d["w"]) * dpr), round(float(d["h"]) * dpr))
        except (KeyError, TypeError, ValueError, OverflowError):
            return web.Response(status=400, text="bad size")
        if not (0 < req[0] <= 20000 and 0 < req[1] <= 20000):
            return web.Response(status=400, text="bad size")
        sid = d.get("sid") if isinstance(d.get("sid"), str) else None
        rec = self.viewers.by_vid.get(sid) if sid else None
        if rec is None:
            rec = self.viewers.by_vid.get(self.viewers.newest())
        if rec is not None and self.seat and not (self.gamemode and self.gamemode.pin):
            self.submit_size(rec, req)
        return web.Response(status=204)

    # -- signaling WebSocket -------------------------------------------------
    async def signaling(self, request):
        if request.headers.get("Upgrade", "").lower() != "websocket":
            return web.Response(status=426, text="websocket upgrade required")
        if not same_origin(request):
            return web.Response(status=403, text="forbidden origin")
        if self.webrtc_off:
            # 409 = selkies' own "server serves WebSockets": the client flips its stored
            # mode back once instead of retrying (a 403 made it reload in a loop).
            self.log("webrtc refused: TURN budget reached, WebSockets only")
            return web.Response(status=409, text="WebRTC is paused (TURN budget reached)")
        qs, sid = split_vid(request.rel_url.raw_query_string, f"wr{uuid.uuid4().hex}")
        now = time.time()
        self._purge(now)
        s = self.sessions.get(sid)
        refuse = None
        if s is not None and s.dead:
            refuse = (FINAL_CODE, b"session ended")
        elif self.busy(sid, now):
            refuse = (refit.BUSY_CODE, b"superseded: in use on another device")
            self.log(f"webrtc reject sid={sid[:8]}: seat in use by another tab")
        if refuse:      # before upstream connects: selkies would kill the active one
            ws = web.WebSocketResponse()
            await ws.prepare(request)
            await ws.close(code=refuse[0], message=refuse[1])
            return ws
        async with aiohttp.ClientSession() as session:
            try:
                up = await session.ws_connect(
                    f"ws://127.0.0.1:{self.live_port()}/api/webrtc/signaling/"
                    + (f"?{qs}" if qs else ""), max_msg_size=0)
            except aiohttp.ClientError:
                return web.Response(status=502, text="stream backend unavailable")
            down = web.WebSocketResponse(max_msg_size=0, heartbeat=HEARTBEAT_S)
            await down.prepare(request)
            s = self.sessions.setdefault(sid, Session(sid, now))
            s.socks.add(down)
            rec = self.attach(sid, down)
            self.touch(now)
            self.write_state()
            self.log(f"webrtc open sid={sid[:8]} (n={self.n})")
            try:
                await asyncio.gather(pump(down, up), pump(up, down), self._watch(s, down),
                                     return_exceptions=True)
            finally:
                s.socks.discard(down)
                s.gone_at = time.time()
                self.detach(sid, down, rec)
                self.write_state()
                self.log(f"webrtc close sid={sid[:8]} (n={self.n})")
                await up.close()
        return down

    async def _watch(self, s: Session, down) -> None:
        while not down.closed:
            why = self.expired(s, time.time())
            if why:
                self.log(f"webrtc {why} sid={s.sid[:8]}: closing and restarting selkies")
                s.dead = True
                for w in list(s.socks):
                    await w.close(code=FINAL_CODE, message=why.encode())
                self.kill(why)
                return
            await asyncio.sleep(min(1.0, self.idle_s or 1.0))
