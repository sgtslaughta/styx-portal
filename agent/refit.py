"""Refit the headless GNOME seat to the browser size (spec: phase 0.5).

The gateway watches the browser's `r,WxH[,display]` messages. Once the size
has held for SETTLE_S and differs from the live seat size (<install>/seat-size) it writes <install>/refit-request
and closes the socket with CLOSE_CODE; the agent rebuilds the virtual monitor at
that size, then clears the request. The injected shim reloads the page once the
gateway serves it again (503 while a request is pending). Pure helpers only."""
import os
import re
import time
from pathlib import Path

CLOSE_CODE = 4002
MIN_W, MIN_H, MAX_W, MAX_H = 640, 480, 3840, 2160
TOLERANCE_PX = 16
MIN_INTERVAL_S = 3.0
SETTLE_S = 1.0          # browser size must hold this long before a refit
_RESIZE = re.compile(r"r,(\d{1,5})x(\d{1,5})(?:,.*)?")
_SIZE = re.compile(r"(\d{1,5})x(\d{1,5})")

RELOAD_JS = (
    '<script id="styx-refit">(function(){var W=window.WebSocket;'
    "function S(u,p){var s=p===undefined?new W(u):new W(u,p);"
    "s.addEventListener('close',function(e){if(e.code!==4002)return;var n=0;"
    "(function poll(){fetch(location.href,{cache:'no-store'}).then(function(r){"
    "if(r.ok)location.reload();else throw 0}).catch(function(){if(++n<60)"
    "setTimeout(poll,500)})})()});return s}"
    "S.prototype=W.prototype;['CONNECTING','OPEN','CLOSING','CLOSED'].forEach("
    "function(k){S[k]=W[k]});window.WebSocket=S})();</script>")


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
    w, h = clamp(*req)
    if current and abs(w - current[0]) <= TOLERANCE_PX and abs(h - current[1]) <= TOLERANCE_PX:
        return None
    if now - last_refit_ts < MIN_INTERVAL_S:
        return None
    return w, h


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
                     sleep=time.sleep, clock=time.monotonic):
    """Sleep up to `timeout`, returning early with a pending request's size.
    An unparsable request file is cleared (else the gateway 503s forever)."""
    end = clock() + timeout
    while True:
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
