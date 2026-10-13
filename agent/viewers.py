"""Per-viewer bookkeeping for the gateway's stream sockets.

A viewer is one browser tab, keyed by its stable `styx_vid` (it survives refit
reconnects); it may briefly hold several sockets while reconnecting."""
from dataclasses import dataclass, field

MAX_VID = 64


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
    socks: set = field(default_factory=set)
    size: tuple | None = None     # last (w, h) from `r,`
    dpi: float | None = None      # last scaling_dpi from SETTINGS
    timer: object = None          # settle-then-refit timer
    gone: object = None           # grace timer once the last socket closed


class Viewers:
    def __init__(self):
        self.by_vid: dict = {}    # insertion order = connect order

    def connect(self, vid, ws) -> Viewer:
        rec = self.by_vid.get(vid)
        if rec is None:
            rec = self.by_vid[vid] = Viewer()
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

    def live(self):
        return [r for r in self.by_vid.values() if r.socks]

    def newest(self):
        """vid of the most recently connected viewer that still has a socket."""
        for vid in reversed(self.by_vid):
            if self.by_vid[vid].socks:
                return vid
        return None
