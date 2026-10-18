"""Run the injected socket proxy in node with a fake WebSocket."""
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
const socks = [], got = [];
class FakeWS { constructor(u){this.url=u;this.readyState=0;socks.push(this);
  setTimeout(()=>{this.readyState=1;this.onopen&&this.onopen({})},0)}
  send(){} close(){} push(d){this.onmessage({data:d})} }
const ctx = {FakeWS, setTimeout, Date, encodeURIComponent, console,
  fetch: () => Promise.resolve({ok:true, headers:{get:()=>null}})};
vm.createContext(ctx);
vm.runInContext(process.argv[2], ctx);
const wait = ms => new Promise(r => setTimeout(r, ms));
(async () => {
  const s = new ctx.S('ws://h/websocket?x=1'); s.onmessage = e => got.push(e.data);
  await wait(10);
  const vid = /styx_vid=(\w+)/.exec(socks[0].url);
  assert(vid && socks[0].url.includes('x=1&styx_vid='), socks[0].url);
  socks[0].push('hello'); socks[0].push(new Uint8Array(3));
  assert.strictEqual(got.length, 2);
  socks[0].push('styx-refit'); socks[0].onclose({code: 4002});
  await wait(300);
  assert.strictEqual(socks.length, 2);
  assert(socks[1].url.includes('styx_vid=' + vid[1]), socks[1].url);
  assert.strictEqual(got.length, 2);
  process.exit(0);
})().catch(e => { console.error(e); process.exit(1); });
"""


def test_proxy_vid_and_reconnect(tmp_path):
    src = refit._proxy(WS="FakeWS", PILL="function(){}", RELOAD="function(){}", LOG="function(){}",
                       VID='"abc123"', PAGE='"http://h/"',
                       INSTALL="this.S=S")
    js = tmp_path / "h.js"
    js.write_text(HARNESS)
    r = subprocess.run(["node", str(js), src], capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stderr


def test_worker_shim_is_valid_js(tmp_path):
    src = refit._WORKER_SHIM.replace("__PAGE__", '"http://h/"').replace("__VID__", '"abc"')
    js = tmp_path / "worker.js"
    js.write_text(src)
    r = subprocess.run(["node", "--check", str(js)], capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stderr


PAGE_HARNESS = r"""
const assert = require('assert'), vm = require('vm');
const [html, navType] = process.argv.slice(2);
const body = html.slice(html.indexOf('>') + 1, html.lastIndexOf('</script>'));
const registry = {}, store = {}, posted = [], workers = [];
function el() {
  const e = {children: [], style: {}, attrs: {}, textContent: '', id: '',
    setAttribute(k, v) { this.attrs[k] = v },
    appendChild(c) { this.children.push(c); if (c.id) registry[c.id] = c; return c },
    remove() { delete registry[this.id] }};
  return e;
}
class FakeBlob { constructor(parts, opts) { this.parts = parts; this.opts = opts } }
class FakeWorker { constructor(u) { this.u = u; this.ls = {}; workers.push(this) }
  addEventListener(t, f) { this.ls[t] = f } postMessage(m) { posted.push([this.u, m]) } }
class FakeWS {}
let n = 0;
const win = {
  document: {getElementById: id => registry[id] || null, createElement: el, body: el(), documentElement: el()},
  sessionStorage: {getItem: k => store[k] ?? null, setItem: (k, v) => { store[k] = v }},
  performance: {getEntriesByType: () => [{type: navType}]},
  location: {search: '?socket_worker=false', href: 'http://h/p', pathname: '/p', hash: '', reload() {}},
  history: {replaceState() {}}, URLSearchParams, Blob: FakeBlob, Worker: FakeWorker, WebSocket: FakeWS,
  crypto: {randomUUID: () => 'uuid' + (++n)}, console, setTimeout, Date, encodeURIComponent, fetch() {},
  URL: {createObjectURL: b => 'blob:' + (b.parts[0].length)},
};
win.window = win; win.document.body.appendChild = win.document.body.appendChild;
vm.createContext(win);
store.styx_vid = 'old';
vm.runInContext(body, win);
const api = win.window.__styxRefit;
assert(api, 'no __styxRefit');
assert.strictEqual(store.styx_vid, navType === 'reload' ? 'old' : 'uuid1');
const marked = new win.Blob(['new WebSocket(m.url)']);
assert(win.Blob === win.window.Blob && marked.parts[0].includes('self.WebSocket=S'));
assert(marked.parts[0].includes(JSON.stringify(store.styx_vid)), 'vid not injected');
assert(!('owner' in api) && !registry['styx-takeover']);
process.exit(0);
"""


@pytest.mark.parametrize("nav", ["reload", "navigate"])
def test_page_shim_runs_in_vm(tmp_path, nav):
    js = tmp_path / "page.js"
    js.write_text(PAGE_HARNESS)
    r = subprocess.run(["node", str(js), refit.RELOAD_JS, nav], capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stderr
