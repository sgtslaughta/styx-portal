"""Run the injected WebRTC shim in node with fake WebSocket/RTCPeerConnection."""
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
const posts = [], socks = [], listeners = {};
class FakeWS { constructor(u) { this.url = String(u); socks.push(this) } addEventListener() {} }
class FakePC { getStats() {
  const m = new Map([
    ['t', {id: 't', type: 'transport', selectedCandidatePairId: 'p1'}],
    ['p1', {id: 'p1', type: 'candidate-pair', localCandidateId: 'l', remoteCandidateId: 'r', bytesReceived: this.rx}],
    ['l', {id: 'l', type: 'local-candidate', candidateType: 'host'}],
    ['r', {id: 'r', type: 'remote-candidate', candidateType: this.remote}]]);
  return Promise.resolve(m) } }
const win = {
  WebSocket: FakeWS, RTCPeerConnection: FakePC, crypto: {randomUUID: () => 'sid-1'},
  document: {visibilityState: 'visible', addEventListener() {}}, navigator: {getGamepads: () => []},
  innerWidth: 1280, innerHeight: 647, devicePixelRatio: 2, encodeURIComponent, console, Date, Math, JSON,
  addEventListener: (e, f) => { (listeners[e] = listeners[e] || []).push(f) },
  fetch: (u, o) => { posts.push([u, JSON.parse(o.body)]); return Promise.resolve() },
  setTimeout, clearTimeout, setInterval: () => 0, String, Promise,
};
win.window = win; win.self = win;
vm.createContext(win);
vm.runInContext(body, win);
new win.WebSocket('wss://h/w/x/api/webrtc/signaling/?a=1');
new win.WebSocket('wss://h/other');
assert.strictEqual(socks[0].url, 'wss://h/w/x/api/webrtc/signaling/?a=1&styx_vid=sid-1');
assert.strictEqual(socks[1].url, 'wss://h/other');
const pc = new win.RTCPeerConnection(); pc.rx = 1000; pc.remote = 'relay';
listeners.keydown[0]({});
setTimeout(() => {
  assert.deepStrictEqual(posts[0], ['styx/activity', {sid: 'sid-1', relay_bytes: 1000, active: true}]);
  pc.rx = 400; // counter went backwards (pair swap): total never decreases
  listeners.pointerdown[0]({});   // within 15 s: trailing, not immediate
  setTimeout(() => { assert.strictEqual(posts.length, 1); console.log('ok'); process.exit(0) }, 20);
}, 30);
"""


def test_webrtc_shim_tags_signaling_and_beacons():
    html = gateway_html.inject_webrtc("<head></head>", True)
    assert "styx-webrtc" in html and gateway_html.inject_webrtc("<head></head>", False) == "<head></head>"
    script = html[html.index("<script"):html.index("</head>")]
    r = subprocess.run(["node", "-e", HARNESS, script], capture_output=True, text=True, timeout=20)
    assert r.returncode == 0 and "ok" in r.stdout, r.stderr
