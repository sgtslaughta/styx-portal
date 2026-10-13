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
              "['mousemove','mousedown','keydown','wheel','touchstart']"
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
