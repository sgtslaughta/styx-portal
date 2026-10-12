"""Refit the headless GNOME seat to the browser size (spec: phase 0.5).

The gateway watches the browser's `r,WxH[,display]` messages. Once the size
has held for SETTLE_S and differs from the live seat size (<install>/seat-size) it writes <install>/refit-request
and closes the socket with CLOSE_CODE; the agent rebuilds the virtual monitor at
that size, then clears the request. The injected shim reloads the page; the gateway
serves HOLD_HTML (which retries) until selkies is back. Pure helpers only."""
import os
import re
import time
from pathlib import Path

CLOSE_CODE = 4002
MIN_W, MIN_H, MAX_W, MAX_H = 640, 480, 4096, 2304   # HiDPI browsers send device px
TOLERANCE_PX = 16
MIN_INTERVAL_S = 3.0
SETTLE_S = 0.6          # browser size must hold this long before a refit
_RESIZE = re.compile(r"r,(\d{1,5})x(\d{1,5})(?:,.*)?")
_SIZE = re.compile(r"(\d{1,5})x(\d{1,5})")

# Spinner overlay shared by the shim (shown on the 4002 close) and HOLD_HTML,
# so the viewer sees one continuous "Resizing…" wait. Single quotes only: it is
# embedded in a JS string.
MARKER = "styx-refit"   # text frame sent just before the refit close
# Refit overlay in the portal's connect-splash style (wave glyph from
# frontend wave-transition.tsx). Single quotes only: embedded in a JS string.
OVERLAY = ("<div id='styx-resizing' style='position:fixed;inset:0;z-index:2147483647;"
           "display:flex;flex-direction:column;align-items:center;justify-content:center;"
           "gap:16px;color:rgba(255,255,255,.9);font:500 14px system-ui,sans-serif;"
           "letter-spacing:.02em;background:radial-gradient(circle at 50% 45%,"
           "#14285a,#0c1730 70%)'>"
           "<svg width='96' height='96' viewBox='0 0 24 24' fill='none' stroke='#fff' "
           "stroke-width='1.6' stroke-linecap='round' stroke-linejoin='round' "
           "style='filter:drop-shadow(0 4px 14px rgba(0,0,0,.35))'>"
           "<path d='M2 6c.6.5 1.2 1 2.5 1C7 7 7 5 9.5 5c2.6 0 2.4 2 5 2 2.5 0 2.5-2 5-2 1.3 0 1.9.5 2.5 1' pathLength='1' style='animation-delay:0.00s'/><path d='M2 12c.6.5 1.2 1 2.5 1 2.5 0 2.5-2 5-2 2.6 0 2.4 2 5 2 2.5 0 2.5-2 5-2 1.3 0 1.9.5 2.5 1' pathLength='1' style='animation-delay:0.12s'/><path d='M2 18c.6.5 1.2 1 2.5 1 2.5 0 2.5-2 5-2 2.6 0 2.4 2 5 2 2.5 0 2.5-2 5-2 1.3 0 1.9.5 2.5 1' pathLength='1' style='animation-delay:0.24s'/></svg><span>Resizing…</span><style>#styx-resizing path{stroke-dasharray:1;"
           "stroke-dashoffset:1;animation:styx-draw 1.6s ease-in-out infinite}"
           "@keyframes styx-draw{0%{stroke-dashoffset:1;opacity:0}15%{opacity:1}"
           "45%,75%{stroke-dashoffset:0;opacity:1}100%{stroke-dashoffset:0;opacity:0}}"
           "</style></div>")

# Poll the page in the background; reload once, when the gateway serves the real
# page again (not HOLD_HTML, which carries X-Styx-Hold).
WAIT_JS = ("function styxWait(){fetch(location.href,{cache:'no-store'}).then(function(r)"
           "{if(r.ok&&!r.headers.get('X-Styx-Hold'))location.reload();else throw 0})"
           ".catch(function(){setTimeout(styxWait,400)})}")
# Last decoded frame, snapshotted before the refit close and kept across the
# reload (sessionStorage), so the viewer sees a frozen desktop + pill instead
# of a splash. WebGL canvases without preserveDrawingBuffer read back black:
# a mostly-black snapshot is dropped and the splash is used instead.
FREEZE_JS = ("function styxFreeze(){try{var c=document.querySelector('canvas,video');"
             "if(!c)return;var k=document.createElement('canvas');k.width=c.videoWidth||c.width;"
             "k.height=c.videoHeight||c.height;var g=k.getContext('2d');g.drawImage(c,0,0);"
             "var d=g.getImageData(0,0,Math.min(k.width,64),Math.min(k.height,64)).data,s=0;"
             "for(var i=0;i<d.length;i+=4)s+=d[i]+d[i+1]+d[i+2];if(s<d.length*4)return;"
             "sessionStorage.setItem('styx-frame',k.toDataURL('image/jpeg',0.7))}catch(e){}}"
             "function styxBg(){try{var f=sessionStorage.getItem('styx-frame');"
             "if(!f)return;var o=document.getElementById('styx-resizing');"
             "o.style.background='#000 url('+f+') center/contain no-repeat';"
             "o.querySelector('svg').style.display='none';var t=o.querySelector('span');"
             "t.style.cssText='position:fixed;bottom:24px;padding:8px 16px;border-radius:999px;"
             "background:rgba(12,23,48,.85);backdrop-filter:blur(6px)'}catch(e){}}")

# The gateway sends MARKER, then closes: show the overlay at once, wait for the
# seat on the close (any code), keep the overlay across the single reload
# (sessionStorage flag; drawn before <body> exists) and lift it 0.8 s after the
# first video frame (audio packets are tiny; selkies resets right after it
# connects). 30 s safety timeout (a seat rebuild + selkies start can take ~10 s).
RELOAD_JS = (
    '<script id="styx-refit">(function(){var W=window.WebSocket,K="styx-resizing";'
    + WAIT_JS + FREEZE_JS +
    "function show(){if(!document.getElementById(K))(document.body||"
    'document.documentElement).insertAdjacentHTML("beforeend","' + OVERLAY + '");styxBg()}'
    "function hide(){try{sessionStorage.removeItem(K);sessionStorage.removeItem('styx-frame')}catch(e){}"
    "var o=document.getElementById(K);if(o)o.remove()}"
    "function arm(){styxFreeze();try{sessionStorage.setItem(K,'1')}catch(e){}show()}"
    "var on=false;try{on=sessionStorage.getItem(K)==='1'}catch(e){}"
    "if(on){show();setTimeout(hide,30000)}"
    "function S(u,p){var s=p===undefined?new W(u):new W(u,p),refit=false;"
    "s.addEventListener('message',function(e){var d=e.data;"
    "if(d==='" + MARKER + "'){refit=true;arm();return}"
    "if(on&&typeof d!=='string'&&(d.byteLength||d.size||0)>2000){on=false;"
    "setTimeout(hide,800)}});"
    "s.addEventListener('close',function(e){if(!refit&&e.code!==4002)return;arm();"
    "styxWait()});return s}"
    "S.prototype=W.prototype;['CONNECTING','OPEN','CLOSING','CLOSED'].forEach("
    "function(k){S[k]=W[k]});window.WebSocket=S})();</script>")
# Served with 200 while the seat is rebuilt: any 5xx would be swapped by Traefik's
# instance-unavailable page, which bounces the viewer to the portal.
HOLD_HTML = ('<!doctype html><html><head><title>Resizing desktop</title></head>'
             '<body id="styx-hold" style="margin:0;background:#0c1730">' + OVERLAY +
             '<script>' + WAIT_JS + FREEZE_JS + 'styxBg();styxWait()</script></body></html>')


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
    """Target size for a refit, or None (close enough, or refitted < 3 s ago)."""
    if not differs(req, current) or now - last_refit_ts < MIN_INTERVAL_S:
        return None
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
    """The first connected viewer owns the seat size; later viewers scale to fit
    (they can take over later via the portal). Released when the owner leaves,
    so the next viewer to resize claims it."""
    def __init__(self):
        self.owner = None

    def claim(self, cid) -> bool:
        if self.owner is None:
            self.owner = cid
        return self.owner == cid

    def release(self, cid) -> None:
        if self.owner == cid:
            self.owner = None
