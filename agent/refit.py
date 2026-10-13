"""Refit the headless GNOME seat to the browser size (spec: phase 0.5).

The gateway watches the browser's `r,WxH[,display]` messages. Once the size
has held for SETTLE_S and differs from the live seat size (<install>/seat-size) it writes <install>/refit-request
and closes the socket with CLOSE_CODE; the agent resizes the virtual monitor in
place and restarts selkies, then clears the request. The injected shim reconnects
transparently (RELOAD_JS); HOLD_HTML covers a full reload. Pure helpers only."""
import json
import os
import re
import time
from pathlib import Path

CLOSE_CODE = 4002
MIN_W, MIN_H, MAX_W, MAX_H = 640, 480, 4096, 2304   # HiDPI browsers send device px
TOLERANCE_PX = 16
MIN_INTERVAL_S = 3.0
SETTLE_S = 0.25         # browser size must hold this long before a refit (client debounces 500 ms first)
_RESIZE = re.compile(r"r,(\d{1,5})x(\d{1,5})(?:,.*)?")
_SIZE = re.compile(r"(\d{1,5})x(\d{1,5})")

MARKER = "styx-refit"   # text frame sent just before the refit close

# Transparent reconnect. selkies 2.0 reads its stream socket in a Web Worker
# (and routes audio packets worker-to-worker, past the page), so the proxy
# below is installed INSIDE that worker: the page shim wraps Blob so the
# worker source selkies builds gets the proxy prepended, and wraps Worker to
# receive its pill/reload requests. The same proxy also replaces the page's
# WebSocket for selkies' page-socket fallback. On the refit marker + close
# the proxy keeps the app's socket object "open", waits for the gateway to
# serve the real page again, reconnects, replays the last SETTINGS and
# START_* commands, and resumes delivering messages. The app never observes a
# close: the last frame stays on the canvas under a small "Resizing…" pill
# until the first frame at the new size arrives.
_PROXY_JS = r"""var W=__WS__,M='styx-refit',SAFETY=30000,PILL=__PILL__,RELOAD=__RELOAD__,LOG=__LOG__;
function S(url,proto){this._url=url;this._proto=proto;this._ls={};this._settings=null;this._starts=[];this._refit=false;this._resuming=false;this._bt='blob';this.readyState=0;this.onopen=this.onmessage=this.onerror=this.onclose=null;this._open()}
S.prototype._open=function(){var self=this,ws=self._proto===undefined?new W(self._url):new W(self._url,self._proto);self._ws=ws;ws.binaryType=self._bt;
ws.onopen=function(e){self.readyState=1;if(self._resuming)self._resume();else self._emit('open',e)};
ws.onmessage=function(e){var d=e.data;if(d===M){self._refit=true;PILL(true);self._t0=Date.now();LOG('[styx] refit: holding socket');return}
if(self._waitFrame&&typeof d!=='string'&&(d.byteLength||d.size||0)>2000){self._waitFrame=false;PILL(false);LOG('[styx] refit: first frame after '+(Date.now()-self._t0)+' ms')}self._emit('message',e)};
ws.onclose=function(e){if(self._refit||e.code===4002){self._refit=false;self._wait();return}self.readyState=3;self._emit('close',e)};
ws.onerror=function(e){if(!self._resuming)self._emit('error',e)}};
S.prototype._wait=function(){var self=this;self._resuming=true;if(Date.now()-(self._t0||0)>SAFETY){RELOAD();return}
fetch(__PAGE__,{cache:'no-store'}).then(function(r){if(r.ok&&!r.headers.get('X-Styx-Hold'))self._open();else throw 0}).catch(function(){setTimeout(function(){self._wait()},100)})};
S.prototype._resume=function(){var ws=this._ws;LOG('[styx] refit: reconnected after '+(Date.now()-this._t0)+' ms');if(this._settings)ws.send(this._settings);for(var i=0;i<this._starts.length;i++)ws.send(this._starts[i]);this._resuming=false;this._waitFrame=true;setTimeout(function(){PILL(false)},SAFETY)};
S.prototype.send=function(d){if(typeof d==='string'){if(d.indexOf('SETTINGS,')===0)this._settings=d;else if(d==='START_VIDEO'||d==='START_AUDIO'){if(this._starts.indexOf(d)<0)this._starts.push(d)}else if(d==='STOP_VIDEO'||d==='STOP_AUDIO'){var i=this._starts.indexOf(d.replace('STOP','START'));if(i>=0)this._starts.splice(i,1)}}
if(this._ws&&this._ws.readyState===1)this._ws.send(d)};
S.prototype.close=function(c,r){this._refit=false;this._resuming=false;this.readyState=2;this._ws&&this._ws.close(c,r)};
S.prototype.addEventListener=function(t,f){(this._ls[t]||(this._ls[t]=[])).push(f)};
S.prototype.removeEventListener=function(t,f){var l=this._ls[t];if(!l)return;var i=l.indexOf(f);i>=0&&l.splice(i,1)};
S.prototype._emit=function(t,e){var h=this['on'+t];h&&h.call(this,e);var l=this._ls[t]||[];for(var i=0;i<l.length;i++)l[i].call(this,e)};
Object.defineProperty(S.prototype,'binaryType',{get:function(){return this._bt},set:function(v){this._bt=v;this._ws&&(this._ws.binaryType=v)}});
Object.defineProperty(S.prototype,'bufferedAmount',{get:function(){return this._ws?this._ws.bufferedAmount:0}});
Object.defineProperty(S.prototype,'url',{get:function(){return this._url}});
Object.defineProperty(S.prototype,'protocol',{get:function(){return this._ws?this._ws.protocol:''}});
Object.defineProperty(S.prototype,'extensions',{get:function(){return this._ws?this._ws.extensions:''}});
S.CONNECTING=0;S.OPEN=1;S.CLOSING=2;S.CLOSED=3;__INSTALL__;
"""

def _proxy(**tokens: str) -> str:
    out = _PROXY_JS
    for k, v in tokens.items():
        out = out.replace(f"__{k}__", v)
    return out

# Inside selkies' socket worker: pill/reload/log go to the page as messages;
# the page URL is injected when the worker source is built.
_WORKER_SHIM = "(function(){" + _proxy(
    WS="self.WebSocket", PILL="function(on){self.postMessage({type:'styx-pill',on:on})}",
    RELOAD="function(){self.postMessage({type:'styx-reload'})}",
    LOG="function(m){self.postMessage({type:'styx-log',m:m})}",
    PAGE="__PAGE__", INSTALL="self.WebSocket=S") + "})();\n"

_PAGE_SHIM = _proxy(
    WS="window.WebSocket", PILL="pill", RELOAD="function(){location.reload()}",
    LOG="function(m){console.log(m)}", PAGE="location.href", INSTALL="window.WebSocket=S")

RELOAD_JS = ('<script id="styx-refit">(function(){var P="styx-resizing",WSRC=' + json.dumps(_WORKER_SHIM) + r""";
function pill(on){var el=document.getElementById(P);if(!on){el&&el.remove();return}if(el)return;el=document.createElement('div');el.id=P;el.textContent='Resizing…';
el.style.cssText='position:fixed;left:50%;bottom:24px;transform:translateX(-50%);z-index:2147483647;padding:8px 16px;border-radius:999px;background:rgba(12,23,48,.85);color:rgba(255,255,255,.9);font:500 14px system-ui,sans-serif;letter-spacing:.02em;backdrop-filter:blur(6px);pointer-events:none';
(document.body||document.documentElement).appendChild(el)}
var B=window.Blob;function SB(parts,opts){if(parts&&typeof parts[0]==='string'&&parts[0].indexOf('new WebSocket(m.url)')>=0)parts=[WSRC.replace('__PAGE__',JSON.stringify(location.href))].concat(parts);return new B(parts,opts)}
SB.prototype=B.prototype;window.Blob=SB;
var K=window.Worker;function SW(u,o){var w=o===undefined?new K(u):new K(u,o);w.addEventListener('message',function(e){var d=e.data;if(!d||typeof d.type!=='string')return;if(d.type==='styx-pill')pill(d.on);else if(d.type==='styx-reload')location.reload();else if(d.type==='styx-log')console.log(d.m)});return w}
SW.prototype=K.prototype;window.Worker=SW;
""" + _PAGE_SHIM + "window.__styxRefit={pill:pill};})();</script>")
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
