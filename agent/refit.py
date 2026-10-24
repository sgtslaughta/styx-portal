"""Refit the headless GNOME seat to the browser size (spec: phase 0.5).

The gateway watches the browser's `r,WxH[,display]` messages. Once the size
has held for SETTLE_S and differs from the live seat size (<install>/seat-size) it writes <install>/refit-request
and aborts every client socket (the browser sees 1006); the agent resizes the
virtual monitor in place and restarts selkies, then clears the request. selkies
2.1 reconnects in place by itself, and the gateway holds the new upgrade until
the request is cleared; HOLD_HTML covers a full reload. Pure helpers only."""
import os
import re
import time
from pathlib import Path

BUSY_CODE = 4003     # gateway refused: another tab holds the seat
MIN_W, MIN_H, MAX_W, MAX_H = 640, 480, 4096, 2304   # HiDPI browsers send device px
TOLERANCE_PX = 16
MIN_INTERVAL_S = 3.0
SETTLE_S = 0.25         # browser size must hold this long before a refit (client debounces 500 ms first)
_RESIZE = re.compile(r"r,(\d{1,5})x(\d{1,5})(?:,.*)?")
_SIZE = re.compile(r"(\d{1,5})x(\d{1,5})")

# Per-tab id. selkies 2.1 reconnects its stream socket by itself, so the only
# job left here is tagging each stream websocket URL with `styx_vid` (the
# gateway's seat hold + size ownership key on it). selkies opens its socket via
# worker.postMessage({type:'open',url,...}); the page-socket fallback goes
# through window.WebSocket. Both are wrapped.
RELOAD_JS = ('<script id="styx-refit">(function(){'
r"""try{var q=new URLSearchParams(location.search);if(q.get('socket_worker')==='false'){q.delete('socket_worker');history.replaceState(null,'',location.pathname+(q.toString()?'?'+q:'')+location.hash)}}catch(e){}
var vid,nav;try{nav=(performance.getEntriesByType('navigation')[0]||{}).type}catch(e){}
if(nav==='reload'||nav==='back_forward'){try{vid=sessionStorage.getItem('styx_vid')}catch(e){}}
if(!vid){try{vid=crypto.randomUUID()}catch(e){vid=Math.random().toString(36).slice(2)+Date.now().toString(36)}try{sessionStorage.setItem('styx_vid',vid)}catch(e){}}
function tag(u){return typeof u==='string'&&u.indexOf('/api/websockets')>=0?u+(u.indexOf('?')<0?'?':'&')+'styx_vid='+encodeURIComponent(vid):u}
var PM=Worker.prototype.postMessage;Worker.prototype.postMessage=function(m){if(m&&typeof m==='object'&&m.type==='open'&&typeof m.url==='string'){m=Object.assign({},m,{url:tag(m.url)});arguments[0]=m}return PM.apply(this,arguments)};
var W=window.WebSocket;function SW(u,p){return p===undefined?new W(tag(u)):new W(tag(u),p)}
SW.prototype=W.prototype;SW.CONNECTING=0;SW.OPEN=1;SW.CLOSING=2;SW.CLOSED=3;window.WebSocket=SW;
})();</script>""")
# Served with 200 while the seat is rebuilt (only reached by a full reload):
# any 5xx would be swapped by Traefik's instance-unavailable page, which
# bounces the viewer to the portal.
HOLD_HTML = ('<!doctype html><html><head><title>Resizing desktop</title></head>'
             '<body id="styx-hold" style="margin:0;background:#0c1730;color:rgba(255,255,255,.9);'
             'font:500 14px system-ui,sans-serif;display:flex;align-items:center;justify-content:center;height:100vh">'
             'Resizing…<script>function styxWait(){fetch(location.href,{cache:\'no-store\'}).then(function(r)'
             '{if(r.ok&&!r.headers.get(\'X-Styx-Hold\'))location.reload();else throw 0})'
             '.catch(function(){setTimeout(styxWait,400)})}styxWait()</script></body></html>')


def clamp(w: int, h: int) -> tuple[int, int]:
    w = min(max(w, MIN_W), MAX_W)
    h = min(max(h, MIN_H), MAX_H)
    return w // 2 * 2, h // 2 * 2


def parse_resize(msg) -> tuple[int, int] | None:
    if not isinstance(msg, str):
        return None
    m = _RESIZE.fullmatch(msg)
    return (int(m[1]), int(m[2])) if m else None


def decide(req, current, last_refit_ts: float, now: float):
    """Target size for a refit, None when close enough, or a float: seconds to
    wait because the last refit was < MIN_INTERVAL_S ago (caller re-arms)."""
    if not differs(req, current):
        return None
    wait = MIN_INTERVAL_S - (now - last_refit_ts)
    if wait > 0:
        return wait
    return clamp(*req)


def differs(req, current) -> bool:
    """Whether the (clamped) browser size is off the live seat size by > 16 px."""
    w, h = clamp(*req)
    return not current or abs(w - current[0]) > TOLERANCE_PX or abs(h - current[1]) > TOLERANCE_PX


def read_size(path) -> tuple[int, int] | None:
    try:
        m = _SIZE.fullmatch(Path(path).read_text().strip())
    except OSError:
        return None
    return (int(m[1]), int(m[2])) if m else None


def write_size(path, w: int, h: int) -> None:
    p = Path(path)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(f"{w}x{h}")
    os.replace(tmp, p)


def request(path, w: int, h: int) -> None:
    write_size(path, w, h)


def pending(path) -> bool:
    return Path(path).exists()


def clear_request(path) -> None:
    Path(path).unlink(missing_ok=True)


def wait_for_request(path, timeout: float, poll: float = 0.25,
                     sleep=time.sleep, clock=time.monotonic, stop=None):
    """Sleep up to `timeout`, returning early with a pending request's size, or
    None as soon as stop() is true. An unparsable request file is cleared."""
    end = clock() + timeout
    while True:
        if stop and stop():
            return None
        req = read_size(path)
        if req:
            return req
        if pending(path):
            clear_request(path)
        left = end - clock()
        if left <= 0:
            return None
        sleep(min(poll, left))


def inject_reload(html: str, enabled: bool) -> str:
    if not enabled or "</head>" not in html:
        return html
    return html.replace("</head>", RELOAD_JS + "</head>", 1)


class SizeOwner:
    """The controller owns the seat size. Released when the owner leaves, so the
    next viewer to resize claims it."""
    def __init__(self):
        self.owner = None

    def claim(self, cid) -> bool:
        if self.owner is None:
            self.owner = cid
        return self.owner == cid

    def release(self, cid) -> None:
        if self.owner == cid:
            self.owner = None
