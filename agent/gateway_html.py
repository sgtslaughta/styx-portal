"""HTML shims injected into the selkies page and websocket message classification (pure helpers)."""
import json


# How long the injected shim reports the tab as visible after load: long
# enough for the selkies client to connect and send START_VIDEO even when
# loaded in a hidden tab, short enough that a backgrounded tab stops
# decoding (its frame queue is unbounded) soon after.
VIS_GRACE_MS = 12000


def inject_title(html: str, hostname: str) -> str:
    """Inject a <head> shim that (1) pins the tab title to the workstation
    hostname and (2) forces the stream to stay live during connection, then
    restores native visibility semantics.

    Title: the selkies client hardcodes `document.title="Selkies"` at init (and
    re-sets it on reconnect), so a one-shot title loses the race. ponytail: a 1s
    poll re-asserts it; drop the interval if upstream stops clobbering it.

    Visibility: the selkies client sends STOP_VIDEO whenever `document.hidden`
    is true and only resumes on a `visibilitychange` back to visible. A page
    that (re)connects while already hidden fires no visibilitychange, so the
    seat stayed on a black "Waiting for stream". Fix: report visible during a
    short connect grace so START_VIDEO always flows, then RESTORE native
    visibility and fire a synthetic visibilitychange. Restoring matters: the
    client's decoded-frame queue is unbounded and only its document.hidden
    check drops frames when the tab is backgrounded — lying forever made
    hidden tabs accumulate VideoFrames for hours (session went sluggish until
    a refresh). With native semantics back, a hidden tab pauses cleanly and
    the next real visibilitychange resumes it.

    Hostname goes through json.dumps -> safe JS string literal (XSS-safe)."""
    script = ("<script>(function(){var t=%s;document.title=t;"
              "setInterval(function(){if(document.title!==t)document.title=t;},1000);"
              "try{Object.defineProperty(document,'hidden',"
              "{configurable:true,get:function(){return false;}});"
              "Object.defineProperty(document,'visibilityState',"
              "{configurable:true,get:function(){return 'visible';}});"
              "window.styxRestoreVisibility=function(){"
              "delete document.hidden;delete document.visibilityState;"
              "document.dispatchEvent(new Event('visibilitychange'));};"
              "setTimeout(window.styxRestoreVisibility,%d);"
              "}catch(e){}})();</script>") % (json.dumps(hostname).replace("<", "\\u003c"), VIS_GRACE_MS)
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
              "window.styxReset=reset;"
              "['mousemove','mousedown','pointerdown','keydown','wheel','touchstart']"
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


# WebRTC page shim. Session id: a fresh uuid per page load, tagged onto the
# signaling WebSocket URL as `styx_vid` (the gateway keys the session on it) and
# sent with every beacon. Beacons: real input while visible -> POST
# styx/activity, leading edge then trailing every 15 s, with the relay bytes
# the client received (cumulative: per-pair peaks summed over every selected
# candidate pair of every peer connection, so it never goes backwards). Every
# 30 s a bytes-only report (active:false) keeps TURN metering honest while idle.
# Resize/fullscreen -> styx/refit {w,h,dpr} (the "r," message rides the data
# channel, which the gateway cannot see). Relative URLs: pages live under /w/<sub>/.
WEBRTC_JS = r"""<script id="styx-webrtc">(function(){
var sid;try{sid=crypto.randomUUID()}catch(e){sid=Math.random().toString(36).slice(2)+Date.now().toString(36)}
var pcs=[],RP=window.RTCPeerConnection;
if(RP){window.RTCPeerConnection=class extends RP{constructor(){super(...arguments);pcs.push(this)}}}
function post(path,body){try{fetch(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body),keepalive:true}).catch(function(){})}catch(e){}}
function refit(){post('styx/refit',{sid:sid,w:innerWidth,h:innerHeight,dpr:devicePixelRatio||1})}
var rt;function refitSoon(){clearTimeout(rt);rt=setTimeout(refit,300)}
addEventListener('resize',refitSoon);document.addEventListener('fullscreenchange',refitSoon);
var W=window.WebSocket;
function SW(u,p){var s=String(u),sig=s.indexOf('/api/webrtc/signaling')>=0;
if(sig)s+=(s.indexOf('?')<0?'?':'&')+'styx_vid='+encodeURIComponent(sid);
var w=p===undefined?new W(s):new W(s,p);if(sig)w.addEventListener('open',refitSoon);return w}
SW.prototype=W.prototype;SW.CONNECTING=0;SW.OPEN=1;SW.CLOSING=2;SW.CLOSED=3;window.WebSocket=SW;
async function relay(){var tot=0;
for(var pc of pcs){var sel=pc.__styxSel||(pc.__styxSel={});
try{var st=await pc.getStats(),by={},cur=null;st.forEach(function(r){by[r.id]=r;if(r.type==='transport'&&r.selectedCandidatePairId)cur=r.selectedCandidatePairId});
st.forEach(function(r){if(r.type!=='candidate-pair')return;
if(!(r.id===cur||r.selected||(cur===null&&r.nominated&&r.state==='succeeded')))return;
var l=by[r.localCandidateId],m=by[r.remoteCandidateId];
if((l&&l.candidateType==='relay')||(m&&m.candidateType==='relay'))sel[r.id]=Math.max(sel[r.id]||0,r.bytesReceived||0)})}catch(e){}
for(var k in sel)tot+=sel[k]}
return tot}
var T=15000,sent=0,rs=0,dirty=false,tm=null;
function send(active){if(active){sent=Date.now();dirty=false}else rs=Date.now();
relay().then(function(rb){post('styx/activity',{sid:sid,relay_bytes:rb,active:active})})}
function act(){if(document.visibilityState!=='visible')return;dirty=true;
var wait=sent+T-Date.now();if(wait<=0)send(true);
else if(!tm)tm=setTimeout(function(){tm=null;if(dirty)send(true)},wait)}
['keydown','pointerdown','pointermove','wheel','touchstart'].forEach(function(e){addEventListener(e,act,{capture:true,passive:true})});
setInterval(function(){try{for(var g of navigator.getGamepads()){if(!g)continue;
if(g.buttons.some(function(b){return b.pressed})||g.axes.some(function(a){return Math.abs(a)>.2})){act();window.styxReset&&window.styxReset();return}}}catch(e){}},1000);
setInterval(function(){if(!dirty&&Date.now()-Math.max(sent,rs)>=30000)send(false)},10000);
})();</script>"""


def inject_webrtc(html: str, enabled: bool) -> str:
    """WebRTC transport only: session tag, input beacons, refit posts (WEBRTC_JS)."""
    if not enabled or "</head>" not in html:
        return html
    return html.replace("</head>", WEBRTC_JS + "</head>", 1)


# Game mode (selkies posts gamingModeUpdate): pin the seat size, and go
# fullscreen on the next click so selkies arms pointer + keyboard lock.
GAMEMODE_JS = r"""<script id="styx-gamemode">(function(){var on=false;
function post(b){try{fetch('styx/gamemode',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(b),keepalive:true}).catch(function(){})}catch(e){}}
addEventListener('message',function(e){try{if(e.source!==window||!e.data||e.data.type!=='gamingModeUpdate')return;
on=!!e.data.active;var d=devicePixelRatio||1;
post(on?{active:true,w:screen.width,h:screen.height,dpr:d}:{active:false,w:innerWidth,h:innerHeight,dpr:d})}catch(x){}});
addEventListener('pointerdown',function(e){try{if(on&&e.button===0&&!document.fullscreenElement)document.documentElement.requestFullscreen({navigationUI:'hide'}).catch(function(){})}catch(x){}},true);
})();</script>"""


def inject_gamemode(html: str) -> str:
    """Both transports: game-mode seat pin + auto-fullscreen (GAMEMODE_JS)."""
    if "</head>" not in html:
        return html
    return html.replace("</head>", GAMEMODE_JS + "</head>", 1)


def inject_favicon(html: str, etag: str) -> str:
    """Replace the selkies tab icon with the workstation icon (styx-favicon, relative: streams live under /w/<sub>/).
    Selkies sets its own <link rel=icon>, so remove those and re-assert ours
    when the head mutates. ponytail: observer + 2s poll backstop; ceiling is
    one querySelectorAll per 2s. `etag` goes through json.dumps with '<'
    escaped, so it cannot close the script tag."""
    href = json.dumps("styx-favicon?v=" + etag).replace("<", "\\u003c")
    script = ("<script>(function(){var h=%s;"
              "function fix(){if(!document.head)return;var ok=false,l=document.querySelectorAll("
              "'link[rel~=\"icon\"],link[rel~=\"apple-touch-icon\"]');"
              "l.forEach(function(e){if(e.getAttribute('href')===h&&!ok){ok=true;}"
              "else e.remove();});"
              "if(!ok){var n=document.createElement('link');n.rel='icon';"
              "n.href=h;document.head.appendChild(n);}}"
              "fix();setInterval(fix,2000);"
              "try{new MutationObserver(fix).observe(document.head,"
              "{childList:true,subtree:true,attributes:true,"
              "attributeFilter:['href','rel']});}catch(e){}"
              "})();</script>") % href
    if "</head>" in html:
        return html.replace("</head>", script + "</head>", 1)
    return script + html


CURSOR_HIDE_CSS = ("<style id=\"styx-cursor\">video,canvas,#videoContainer,"
                   "#overlayInput{cursor:none !important}"
                   # selkies 2.0 client-drawn cursor: an id-less fixed canvas
                   # appended to <body> with z-index 999999.
                   'body>canvas[style*="999999"]{display:none !important}'
                   "</style>")


def inject_cursor_hide(html: str, enabled: bool) -> str:
    """GNOME portal capture bakes the cursor into the video and sends no cursor
    metadata, so the browser cursor doubles it (flicker, stale cursor on leave).
    Hide the browser one; the in-video cursor is the only cursor (spec 5.2)."""
    if not enabled or "</head>" not in html:
        return html
    return html.replace("</head>", CURSOR_HIDE_CSS + "</head>", 1)


TOUCH_SCROLL_JS = (
    "<script>(function(){"
    "function patch(inp){"
    "if(!inp||inp.__styxTouchScroll||typeof inp._twoFingerMove!=='function'"
    "||typeof inp._endFingerScroll!=='function')return;"
    "inp.__styxTouchScroll=1;var orig=inp._twoFingerMove;"
    "inp._twoFingerMove=function(x1,y1,x2,y2){var g=this._twoFinger;"
    "if(!this.fingerScroll||!g||g.kind!=='scroll')return orig.apply(this,arguments);"
    "var a=(x1+x2)/2,o=(y1+y2)/2,s=this._pointerScale(),"
    "dx=g.rail!=='y'?(g.x-a)*s.x:0,dy=g.rail!=='x'?(g.y-o)*s.y:0;g.x=a;g.y=o;"
    "if(!dx&&!dy)return;this.send('sf,'+dx.toFixed(2)+','+dy.toFixed(2));"
    "var self=this;clearTimeout(this._fingerScrollTimer);"
    "this._fingerScrollTimer=setTimeout(function(){self._endFingerScroll();},200);};"
    "function end(e){if(e.touches.length<2&&inp._fingerScrollTimer!==null)inp._endFingerScroll();}"
    "document.addEventListener('touchend',end,true);"
    "document.addEventListener('touchcancel',end,true);}"
    "setInterval(function(){patch(window.webrtcInput);},500);"
    "})();</script>")


def inject_touch_scroll(html: str) -> str:
    """A touchscreen's two-finger scroll goes out as selkies' finger scroll
    (`sf` deltas, `sfe` on lift) instead of one wheel notch per 50 px: smooth,
    and the lift is the axis stop GNOME starts its kinetic scroll on. Selkies
    2.1 sends `sf` only for a touchpad's wheel events; the page already holds
    `fingerScroll` from the server's display config, so a session without
    finger scroll keeps the notches. ponytail: patches minified client
    internals (_twoFingerMove, _endFingerScroll); a client lacking them is
    left alone. Drop once upstream routes touch scroll through sf (issue TBD)."""
    if "</head>" not in html:
        return html
    return html.replace("</head>", TOUCH_SCROLL_JS + "</head>", 1)


def is_activity(data) -> bool:
    """Whether a client->server message counts as user activity for idle timing.

    Selkies multiplexes protocol/telemetry with input on one channel; counting
    the automated traffic resets the idle clock continuously so the seat never
    times out. The command token (text before the first comma) tells them apart:
      - ALL-CAPS commands are protocol, all automated: CLIENT_FRAME_ACK (one per
        video frame — the dominant resetter), START_AUDIO, START/STOP_VIDEO,
        SETTINGS, SESSION, SET_NATIVE_CURSOR_RENDERING, FILE_UPLOAD_ERROR.
      - '_'-prefixed are internal stats on a timer (_f framerate ~5s, _crf, _rc).
      - 'pong' is the keepalive reply to the server ping.
    Real user input uses lowercase codes — mouse 'm2', keyboard, clipboard 'cw',
    resize 'r'/'s' — and binary frames. Those count.

    Caps-token rule (not an explicit blocklist) so a new protocol command can't
    silently re-break idle."""
    if not isinstance(data, str):
        return True
    cmd = data.split(",", 1)[0]
    return not (cmd.isupper() or cmd.startswith("_") or cmd == "pong")


def is_bare_motion(data) -> bool:
    """A pointer move with no button held and no wheel ('m'/'m2',x,y,0,0...).
    With the browser-drawn cursor it changes nothing on screen, so a still
    desktop answers it with no frames: it must not re-arm the stall watchdog."""
    if not isinstance(data, str):
        return False
    t = data.split(",")
    return t[0] in ("m", "m2") and len(t) >= 5 and t[3] == "0" and t[4] == "0"
