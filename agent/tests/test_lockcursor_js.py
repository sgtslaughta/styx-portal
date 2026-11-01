"""Pointer-locked cursor overlay shim (LOCKCURSOR_JS), run in node with fakes."""
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import gateway_html  # noqa: E402

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node missing")

HARNESS = r"""
const assert = require('assert'), vm = require('vm');
const html = process.argv[process.argv.length - 1];
const body = html.slice(html.indexOf('>') + 1, html.lastIndexOf('</script>'));
const win = {}, docL = {}, winL = {}, sent = [];
const imgs = [];
const doc = {
  pointerLockElement: null,
  addEventListener: (e, f) => { docL[e] = f },
  createElement: () => { const i = {style: {}, attrs: {}, setAttribute(k, v) { this.attrs[k] = v },
                                   getAttribute(k) { return this.attrs[k] }}; imgs.push(i); return i },
  body: {appendChild() {}},
};
const input = {
  send: (m) => sent.push(m),
  element: {getBoundingClientRect: () => ({left: 0, top: 0, right: 1280, bottom: 720})},
  _cursorBase64Data: 'QUJD', cursorHotspot: {x: 2, y: 3}, displayId: 'primary',
  _streamBox: () => ({left: 10, top: 20, width: 1280, height: 720, scaleX: 2, scaleY: 2}),
  _pointerSeq: 0,
  _sendPointer(e) { this._pointerSeq += 1; this.send(e.join(',') + ',' + this._pointerSeq) },
  echoes: [], onPointerEcho(m) { this.echoes.push(m) },
};
Object.assign(win, {document: doc, Math, setInterval: () => 0,
  addEventListener: (e, f) => { winL[e] = f }, webrtcInput: input});
win.window = win;
vm.createContext(win);
vm.runInContext(body, win);
winL.mousemove({clientX: 100, clientY: 200});       // unlocked: remember the spot
doc.pointerLockElement = {};
docL.pointerlockchange();                            // lock: overlay at that spot, echo on
const img = imgs[0];
assert.strictEqual(img.style.display, 'block');
assert.strictEqual(img.attrs.src, 'data:image/png;base64,QUJD');
assert.strictEqual(img.style.transform, 'translate(98px,197px)');
winL.mousemove({movementX: 50, movementY: -20});    // no echo yet: deltas move it 1:1
assert.strictEqual(img.style.transform, 'translate(148px,177px)');
winL.mousemove({movementX: -5000, movementY: 0});   // clamped to the stream
assert.strictEqual(img.style.transform, 'translate(-2px,177px)');
// the server-side embedded-cursor switch never reaches selkies; other input does
win.webrtcInput.send('SET_NATIVE_CURSOR_RENDERING,1');
win.webrtcInput.send('p,1');
win.webrtcInput.send('m2,3,4,0,0');
assert.deepStrictEqual(sent, ['_pointer_echo,1', 'm2,3,4,0,0']);
// a lock's first echo is held until the position moves (a stale seat repeats 0,0)
win.webrtcInput.onPointerEcho('pointer,primary,0.0,0.0,1,0');
assert.strictEqual(img.style.transform, 'translate(-2px,177px)');
// server position + the relative moves sent after the echo's seq, in server pixels
win.webrtcInput._sendPointer(['m2', 10, 5]);         // seq 1, not yet in an echo
win.webrtcInput.onPointerEcho('pointer,primary,500,300,1,0');
assert.strictEqual(img.style.transform, 'translate(263px,169.5px)');    // 10+(500+10)/2-2, 20+(300+5)/2-3
win.webrtcInput.onPointerEcho('pointer,primary,510,305,1,1');          // seq 1 applied: no double count
assert.strictEqual(img.style.transform, 'translate(263px,169.5px)');
win.webrtcInput.onPointerEcho('pointer,primary,900,100,1,1');          // a game warp: follow it
assert.strictEqual(img.style.transform, 'translate(458px,67px)');
winL.mousemove({movementX: 7, movementY: 7});       // echo known: local deltas do not drift it
assert.strictEqual(img.style.transform, 'translate(458px,67px)');
win.webrtcInput.onPointerEcho('pointer,other,0,0,1,9');                // another display: ignored
win.webrtcInput.onPointerEcho('pointer,none');
assert.strictEqual(img.style.transform, 'translate(458px,67px)');
assert.strictEqual(input.echoes.length, 6);                             // selkies still sees them all
input._cursorBase64Data = null;                     // remote cursor hidden (games)
winL.mousemove({movementX: 1, movementY: 1});
assert.strictEqual(img.style.display, 'none');
input._cursorBase64Data = 'QUJD';
doc.pointerLockElement = null;                       // unlock: overlay gone, echo off
docL.pointerlockchange();
assert.strictEqual(img.style.display, 'none');
assert.strictEqual(sent[sent.length - 1], '_pointer_echo,0');
console.log('ok');
"""


def test_lock_cursor_overlay_and_native_switch_dropped():
    html = gateway_html.inject_gamemode("<head></head>")
    assert "styx-lockcursor" in html and "styx-gamemode" in html
    script = html[html.index('<script id="styx-lockcursor">'):]
    script = script[:script.index("</script>") + len("</script>")]
    r = subprocess.run(["node", "-e", HARNESS, script], capture_output=True, text=True, timeout=30)
    assert r.returncode == 0 and "ok" in r.stdout, r.stderr
