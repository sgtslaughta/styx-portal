"""Game mode: while selkies is in game mode the seat size is pinned, so browser
fullscreen resizes do not refit (and restart) the seat mid pointer-lock."""
import json

from aiohttp import web

from gateway_ws import same_origin


class GameMode:
    def __init__(self, viewers, size_owner, submit_size, seat: bool, log=print):
        self.pin = None
        self.viewers, self.size_owner, self.submit_size = viewers, size_owner, submit_size
        self.seat, self.log = seat, log

    async def handle(self, request):
        """POST /styx/gamemode {active, w, h, dpr?}."""
        if not same_origin(request):
            return web.Response(status=403, text="forbidden origin")
        try:
            d = json.loads(await request.content.read(4096))
            dpr = float(d.get("dpr", 1))
            req = (round(float(d["w"]) * dpr), round(float(d["h"]) * dpr))
            ok = 0 < req[0] <= 20000 and 0 < req[1] <= 20000
        except (ValueError, AttributeError, KeyError, TypeError, OverflowError):
            ok = False
        if not ok:
            return web.Response(status=400, text="bad size")
        on = d.get("active") is True
        self.pin = req if on else None
        self.log(f"gamemode {'on: seat pinned at' if on else 'off: seat released to'} {req[0]}x{req[1]}")
        rec = self.viewers.by_vid.get(self.size_owner.owner) or self.viewers.by_vid.get(self.viewers.newest())
        if rec is not None and self.seat:
            self.submit_size(rec, req)
        return web.Response(status=204)
