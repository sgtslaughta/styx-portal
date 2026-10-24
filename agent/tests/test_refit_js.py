"""Run the injected tab-id tagger in node with fake Worker/WebSocket."""
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import refit  # noqa: E402

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node missing")

HARNESS = r"""
const assert = require('assert'), vm = require('vm');
const [html, navType] = process.argv.slice(2);
const body = html.slice(html.indexOf('>') + 1, html.lastIndexOf('</script>'));
const store = {}, posted = [], socks = [];
class FakeWorker { postMessage(m) { posted.push(m) } }
class FakeWS { constructor(u, p) { this.url = u; this.p = p; socks.push(this) } }
FakeWS.CONNECTING = 0; FakeWS.OPEN = 1; FakeWS.CLOSING = 2; FakeWS.CLOSED = 3;
let n = 0;
const win = {
  sessionStorage: {getItem: k => store[k] ?? null, setItem: (k, v) => { store[k] = v }},
  performance: {getEntriesByType: () => [{type: navType}]},
  location: {search: '?socket_worker=false', pathname: '/p', hash: ''},
  history: {replaceState() {}}, URLSearchParams, Worker: FakeWorker, WebSocket: FakeWS,
  crypto: {randomUUID: () => 'uuid' + (++n)}, console, encodeURIComponent,
};
win.window = win;
vm.createContext(win);
store.styx_vid = 'old';
vm.runInContext(body, win);
const vid = store.styx_vid;
assert.strictEqual(vid, navType === 'reload' ? 'old' : 'uuid1');
const w = new win.Worker();
w.postMessage({type: 'open', url: 'wss://h/api/websockets?x=1', primary: true});
w.postMessage({type: 'open', url: 'wss://h/api/websockets'});
w.postMessage({type: 'open', url: 'wss://h/other'});
w.postMessage({type: 'data', url: 'wss://h/api/websockets'});
w.postMessage('open');
assert.strictEqual(posted[0].url, 'wss://h/api/websockets?x=1&styx_vid=' + vid);
assert.strictEqual(posted[0].primary, true);
assert.strictEqual(posted[1].url, 'wss://h/api/websockets?styx_vid=' + vid);
assert.strictEqual(posted[2].url, 'wss://h/other');
assert.strictEqual(posted[3].url, 'wss://h/api/websockets');
assert.strictEqual(posted[4], 'open');
new win.WebSocket('wss://h/api/websockets', ['p']);
assert.strictEqual(socks[0].url, 'wss://h/api/websockets?styx_vid=' + vid);
assert.deepStrictEqual(socks[0].p, ['p']);
new win.WebSocket('wss://h/x');
assert.strictEqual(socks[1].url, 'wss://h/x');
assert(win.WebSocket.prototype === FakeWS.prototype);
assert.strictEqual(win.WebSocket.OPEN, 1);
assert.strictEqual(win.WebSocket.CLOSED, 3);
process.exit(0);
"""


@pytest.mark.parametrize("nav", ["reload", "navigate"])
def test_tagger_runs_in_vm(tmp_path, nav):
    js = tmp_path / "page.js"
    js.write_text(HARNESS)
    r = subprocess.run(["node", str(js), refit.RELOAD_JS, nav], capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stderr
