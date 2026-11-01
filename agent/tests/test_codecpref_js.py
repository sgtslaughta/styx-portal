"""Hardware-codec-first answer shim (CODECPREF_JS), run in node with fakes."""
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import codecpref  # noqa: E402

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node missing")

HARNESS = r"""
const assert = require('assert'), vm = require('vm');
const html = process.argv[process.argv.length - 1];
const body = html.slice(html.indexOf('>') + 1, html.lastIndexOf('</script>'));
const SDP = 'v=0\r\nm=video 9 UDP/TLS/RTP/SAVPF 45 46 49 102\r\n' +
  'a=rtpmap:45 AV1/90000\r\na=rtpmap:46 rtx/90000\r\na=rtpmap:49 H265/90000\r\na=rtpmap:102 H264/90000\r\n';
const CAPS = ['video/VP8', 'video/rtx', 'video/H264', 'video/AV1', 'video/H265'].map((m) => ({mimeType: m}));
async function run(hwSet, sdp) {
  const prefs = [], posts = [], answered = [];
  function PC() {}
  PC.prototype.createAnswer = function () { answered.push(prefs.length); return Promise.resolve({type: 'answer'}) };
  PC.prototype.getTransceivers = function () {
    return [{receiver: {track: {kind: 'video'}}, setCodecPreferences: (c) => prefs.push(c.map((x) => x.mimeType))},
            {receiver: {track: {kind: 'audio'}}, setCodecPreferences: () => { throw new Error('audio touched') }}];
  };
  const win = {
    RTCPeerConnection: PC, Promise, RegExp, setTimeout,
    RTCRtpReceiver: {getCapabilities: () => ({codecs: CAPS})},
    navigator: {mediaCapabilities: {decodingInfo: (c) => Promise.resolve(
      {supported: true, powerEfficient: hwSet.includes(c.video.contentType)})}},
    fetch: (u, o) => { posts.push(JSON.parse(o.body)); return Promise.resolve() },
  };
  win.window = win;
  vm.createContext(win);
  vm.runInContext(body, win);
  const pc = new PC();
  pc.remoteDescription = {sdp};
  await pc.createAnswer();
  return {prefs, posts, answered};
}
(async () => {
  // HEVC in hardware, AV1 offered first: HEVC first, then the rest in offer order
  let r = await run(['video/h265'], SDP);
  assert.deepStrictEqual(r.prefs, [['video/H265', 'video/AV1', 'video/H264', 'video/VP8', 'video/rtx']]);
  assert.deepStrictEqual(r.answered, [1]);                       // reordered before the answer
  assert.deepStrictEqual(r.posts[0].diag.codecpref, ['video/h265', 'video/av1', 'video/h264']);
  // nothing in hardware: answer untouched
  r = await run([], SDP);
  assert.deepStrictEqual(r.prefs, []);
  assert.deepStrictEqual(r.answered, [0]);
  // AV1 in hardware and offered first: untouched
  r = await run(['video/av1', 'video/h265'], SDP);
  assert.deepStrictEqual(r.prefs, []);
  // no video m-line: untouched
  r = await run(['video/h265'], 'v=0\r\n');
  assert.deepStrictEqual(r.prefs, []);
  console.log('ok');
})().catch((e) => { console.error(e); process.exit(1) });
"""


def test_hardware_codec_first_in_answer():
    html = codecpref.inject_codecpref("<head></head>")
    script = html[html.index('<script id="styx-codecpref">'):]
    script = script[:script.index("</script>") + len("</script>")]
    r = subprocess.run(["node", "-e", HARNESS, script], capture_output=True, text=True, timeout=30)
    assert r.returncode == 0 and "ok" in r.stdout, r.stderr


def test_inject_needs_head():
    assert codecpref.inject_codecpref("<body></body>") == "<body></body>"
