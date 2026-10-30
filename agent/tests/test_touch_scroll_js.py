"""Run the injected touch-scroll shim in node against a fake selkies input."""
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import gateway_html  # noqa: E402

HARNESS = r"""
const assert = require('assert'), vm = require('vm');
const html = process.argv[2];
const body = html.slice(html.indexOf('<script>') + 8, html.lastIndexOf('</script>'));
let tick = null, timers = 0;
const listeners = {}, sent = [], origCalls = [];
const inp = {
  fingerScroll: true, _fingerScrollTimer: null,
  _twoFinger: {kind: 'scroll', rail: 'y', x: 50, y: 100},
  _pointerScale() { return {x: 2, y: 2}; },
  send(m) { sent.push(m); },
  _twoFingerMove(...a) { origCalls.push(a); },
  _endFingerScroll() { if (this._fingerScrollTimer !== null) { this._fingerScrollTimer = null; this.send('sfe'); } },
};
const win = {
  setInterval: f => { tick = f; }, setTimeout: () => ++timers, clearTimeout() {},
  document: {addEventListener: (t, f) => { (listeners[t] = listeners[t] || []).push(f); }},
  webrtcInput: inp,
};
win.window = win;
vm.createContext(win);
vm.runInContext(body, win);
tick(); tick();                                   // idempotent: wrapped once
inp._twoFingerMove(40, 70, 60, 70);               // midpoint (50,70): finger up 30 css px
assert.deepStrictEqual(sent, ['sf,0.00,60.00']);  // scroll down 60 stream px, rail y
assert.strictEqual(origCalls.length, 0);
assert.strictEqual(listeners.touchend.length, 1);
listeners.touchend[0]({touches: [1, 2]});         // still two fingers: no end
assert.strictEqual(sent.length, 1);
listeners.touchend[0]({touches: [1]});            // lift: end -> momentum
assert.deepStrictEqual(sent, ['sf,0.00,60.00', 'sfe']);
inp._twoFinger = {kind: null, x: 0, y: 0};        // unclassified: upstream decides
inp._twoFingerMove(1, 2, 3, 4);
inp._twoFinger = {kind: 'pinch', x: 0, y: 0};
inp._twoFingerMove(1, 2, 3, 4);
inp.fingerScroll = false; inp._twoFinger = {kind: 'scroll', rail: 'xy', x: 0, y: 0};
inp._twoFingerMove(1, 2, 3, 4);
assert.strictEqual(origCalls.length, 3);
assert.strictEqual(sent.length, 2);
process.exit(0);
"""


def test_inject_touch_scroll():
    html = "<html><head></head><body></body></html>"
    out = gateway_html.inject_touch_scroll(html)
    assert out.count("<script>") == 1 and out.index("<script>") < out.index("</head>")
    assert gateway_html.inject_touch_scroll("<p>no head</p>") == "<p>no head</p>"


@pytest.mark.skipif(shutil.which("node") is None, reason="node missing")
def test_touch_scroll_shim_runs_in_vm(tmp_path):
    js = tmp_path / "page.js"
    js.write_text(HARNESS)
    html = gateway_html.inject_touch_scroll("<head></head>")
    r = subprocess.run(["node", str(js), html], capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stderr
