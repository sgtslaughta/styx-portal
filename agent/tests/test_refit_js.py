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
const socks = [], calls = [], got = [];
class FakeWS { constructor(u){this.url=u;this.readyState=0;socks.push(this);
  setTimeout(()=>{this.readyState=1;this.onopen&&this.onopen({})},0)}
  send(){} close(){} push(d){this.onmessage({data:d})} }
const ctx = {FakeWS, calls, setTimeout, Date, encodeURIComponent, console,
  fetch: () => Promise.resolve({ok:true, headers:{get:()=>null}})};
vm.createContext(ctx);
vm.runInContext(process.argv[2], ctx);
const wait = ms => new Promise(r => setTimeout(r, ms));
(async () => {
  const s = new ctx.S('ws://h/websocket?x=1'); s.onmessage = e => got.push(e.data);
  await wait(10);
  const vid = /styx_vid=(\w+)/.exec(socks[0].url);
  assert(vid && socks[0].url.includes('x=1&styx_vid='), socks[0].url);
  socks[0].push('styx-owner,0');
  assert.deepStrictEqual(calls, [false]); assert.deepStrictEqual(got, []);
  socks[0].push('hello'); socks[0].push(new Uint8Array(3));
  assert.strictEqual(got.length, 2);
  socks[0].push('styx-refit'); socks[0].onclose({code: 4002});
  await wait(300);
  assert.strictEqual(socks.length, 2);
  assert(socks[1].url.includes('styx_vid=' + vid[1]), socks[1].url);
  socks[1].push('styx-owner,1');
  assert.deepStrictEqual(calls, [false, true]); assert.strictEqual(got.length, 2);
  process.exit(0);
})().catch(e => { console.error(e); process.exit(1); });
"""


def test_proxy_vid_owner_and_reconnect(tmp_path):
    src = refit._proxy(WS="FakeWS", PILL="function(){}", RELOAD="function(){}", LOG="function(){}",
                       OWNER="function(on){calls.push(on)}", VID='"abc123"', PAGE='"http://h/"',
                       INSTALL="this.S=S")
    js = tmp_path / "h.js"
    js.write_text(HARNESS)
    r = subprocess.run(["node", str(js), src], capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stderr
