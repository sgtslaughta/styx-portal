"""Per-viewer bookkeeping for the gateway's stream sockets.

A viewer is one browser tab, keyed by its stable `styx_vid` (it survives refit
reconnects); it may briefly hold several sockets while reconnecting."""
from dataclasses import dataclass, field

MAX_VID = 64
STALL_LOG_S = 1.0       # client silent this long while video is on -> log it


def split_vid(raw_qs: str, fallback: str):
    """Return (query string without styx_vid, vid). The vid never reaches selkies."""
    vid, keep = "", []
    for part in raw_qs.split("&"):
        if part.startswith("styx_vid="):
            vid = part[9:][:MAX_VID]
        elif part:
            keep.append(part)
    return "&".join(keep), vid or fallback


@dataclass
class Viewer:
    vid: str = ""
    socks: set = field(default_factory=set)
    size: tuple | None = None     # last (w, h) from `r,`
    dpi: float | None = None      # last scaling_dpi from SETTINGS
    timer: object = None          # settle-then-refit timer
    gone: object = None           # grace timer once the last socket closed
    shared: bool = False          # selkies `role=viewer`: read-only, never owns the size
    last_input: float = 0.0       # last real input from this tab (0 = none yet)


class Viewers:
    def __init__(self):
        self.by_vid: dict = {}    # insertion order = connect order

    def connect(self, vid, ws) -> Viewer:
        rec = self.by_vid.get(vid)
        if rec is None:
            rec = self.by_vid[vid] = Viewer(vid)
        elif not rec.socks:       # returning after a full close: newest again
            self.by_vid[vid] = self.by_vid.pop(vid)
        if rec.gone:
            rec.gone.cancel()
            rec.gone = None
        rec.socks.add(ws)
        return rec

    def disconnect(self, vid, ws) -> bool:
        """True when the vid has no live socket left."""
        rec = self.by_vid.get(vid)
        if rec is None:
            return True
        rec.socks.discard(ws)
        return not rec.socks

    def drop(self, vid) -> None:
        rec = self.by_vid.pop(vid, None)
        if rec:
            for h in (rec.timer, rec.gone):
                h and h.cancel()

    def busy(self, vid, now: float, hold_s: float) -> bool:
        """Another controller tab is connected and had input within hold_s."""
        return any(not r.shared and r.vid != vid and now - r.last_input < hold_s
                   for r in self.live())

    def live(self):
        return [r for r in self.by_vid.values() if r.socks]

    def newest(self):
        """vid of the most recently connected controller that still has a socket."""
        for vid in reversed(self.by_vid):
            if self.by_vid[vid].socks and not self.by_vid[vid].shared:
                return vid
        return None


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
