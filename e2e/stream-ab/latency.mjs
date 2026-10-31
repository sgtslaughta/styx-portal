// Input-to-photon latency of the live seat stream, one run. Prints raw JSON (latstats.py derives the stats).
//   STYX_USER=U STYX_PASS=P node latency.mjs --url=http://127.0.0.1:18443/ [--n=100]
// Per input (key F8, mouse button, pointer motion) and sample: t0 = performance.now() when the page
// receives the input (capture listener), `dec` = first decoded VideoFrame whose pixels show the change
// (the run.mjs metric), `pres` = first frame PRESENTED by the <video> sink (requestVideoFrameCallback,
// metadata.expectedDisplayTime, else presentationTime, else the callback time) that shows it.
// Pixels come from a 1x1 drawImage of the frame at a point inside the workload.html square/block.
// Then 15 s of the animation (F9) record presented-frame times for stalls and pacing.
// ponytail: no seat-side timestamp; a stuck compositor would still read as "presented".
import { chromium } from 'playwright';

const a = Object.fromEntries(process.argv.slice(2).map(s => s.replace(/^--/, '').split(/=(.*)/s).slice(0, 2)));
const N = Number(a.n || 100), sleep = ms => new Promise(r => setTimeout(r, ms));
const rand = (lo, hi) => lo + Math.random() * (hi - lo);   // 150-400 ms: never locked to the frame clock
const VW = 1280, VH = 720;
const PTS = {                                              // workload.html, CSS px
  key: { key: [100, 250] },                                // #flip
  mouse: { mouse: [100, 470] },                            // #mflip
  motion: { mA: [900, 300], mB: [1000, 500] },             // #blk (200 px) centred on the pointer
};

const browser = await chromium.launch();
const ctx = await browser.newContext({
  httpCredentials: { username: process.env.STYX_USER, password: process.env.STYX_PASS },
  viewport: { width: VW, height: VH }, deviceScaleFactor: 2,
});
await ctx.addInitScript(([VW, VH]) => {
  const px = new OffscreenCanvas(1, 1).getContext('2d', { willReadFrequently: true });
  Object.assign(self, { __pts: {}, __dec: {}, __A: null, __rec: false, __pt: [], __nPres: 0, __nDec: 0 });
  const luma = (src, w, h, x, y) => {
    try {
      px.drawImage(src, x * w / VW, y * h / VH, 1, 1, 0, 0, 1, 1);
      const d = px.getImageData(0, 0, 1, 1).data;
      return 0.299 * d[0] + 0.587 * d[1] + 0.114 * d[2];
    } catch (e) { return null; }                           // closed frame
  };
  const changed = (A, l) => l !== null && A.base !== undefined && Math.abs(l - A.base) > 80;
  const write = WritableStreamDefaultWriter.prototype.write;
  WritableStreamDefaultWriter.prototype.write = function (chunk) {
    // selkies re-writes its last frame about every 1.2 s when idle: only a new timestamp is a new frame.
    if (chunk instanceof VideoFrame && chunk.timestamp !== self.__lastTs) {
      self.__lastTs = chunk.timestamp; self.__nDec++;
      const now = performance.now();
      for (const [n, [x, y]] of Object.entries(self.__pts)) {
        const l = luma(chunk, chunk.displayWidth, chunk.displayHeight, x, y);
        if (l !== null) self.__dec[n] = l;
      }
      const A = self.__A;
      if (A && A.t0 !== null && A.dec === null && changed(A, self.__dec[A.name])) A.dec = now;
    }
    return write.call(this, chunk);
  };
  const onPresent = (now, md, src, w, h) => {
    self.__nPres++;
    const tp = md && md.expectedDisplayTime > 0 ? md.expectedDisplayTime
      : md && md.presentationTime > 0 ? md.presentationTime : now;
    if (self.__rec) self.__pt.push(tp);
    const A = self.__A;
    if (A && A.t0 !== null && A.pres === null) {
      const [x, y] = self.__pts[A.name];
      if (changed(A, luma(src, w, h, x, y))) { A.pres = tp; A.presCb = now; A.done(); }
    }
  };
  self.__startPresent = () => {                            // 'video' (rVFC) or 'raf' fallback
    const v = document.getElementById('videoStream');
    if (v && v.tagName === 'VIDEO' && v.requestVideoFrameCallback) {
      const cb = (now, md) => { onPresent(now, md, v, v.videoWidth, v.videoHeight); v.requestVideoFrameCallback(cb); };
      v.requestVideoFrameCallback(cb);
      return 'video';
    }
    const raf = now => {
      const s = document.getElementById('videoStream') || document.getElementById('videoCanvas');
      if (s && (s.videoWidth || s.width)) onPresent(now, null, s, s.videoWidth || s.width, s.videoHeight || s.height);
      requestAnimationFrame(raf);
    };
    requestAnimationFrame(raf);
    return 'raf';
  };
  self.__arm = (name, timeout) => new Promise(res => {
    const A = { name, base: self.__dec[name], t0: null, dec: null, pres: null, presCb: null };
    A.done = () => { clearTimeout(A.to); if (self.__A === A) self.__A = null; res({ t0: A.t0, dec: A.dec, pres: A.pres, presCb: A.presCb }); };
    A.to = setTimeout(A.done, timeout);
    self.__A = A;
  });
  for (const t of ['keydown', 'mousedown', 'mousemove'])    // runs first: registered before selkies'
    addEventListener(t, () => { const A = self.__A; if (A && A.t0 === null) A.t0 = performance.now(); }, true);
});
const page = await ctx.newPage();
await page.goto(a.url);
await page.waitForFunction(() => [...document.querySelectorAll('#videoStream, #videoCanvas')]
  .some(e => e.offsetWidth > 0 && getComputedStyle(e).display !== 'none'), null, { timeout: 30000 });
let sink = await page.evaluate(() => window.__startPresent());
await sleep(4000);                                         // first frames + paint-over
if (sink === 'video' && !(await page.evaluate(() => window.__nPres))) {
  sink = 'raf';                                            // video element never presented: sample from rAF
  await page.evaluate(() => { const v = document.getElementById('videoStream'); v.requestVideoFrameCallback = undefined; window.__startPresent(); });
}

async function run(kind, fire) {
  await page.evaluate(p => { window.__pts = p; window.__dec = {}; }, PTS[kind]);
  await sleep(1500);                                       // baseline frames at the new sample points
  const out = [];
  for (let i = 0; i < N + 1; i++) {                        // sample 0 settles the page state, not recorded
    const name = Object.keys(PTS[kind])[kind === 'motion' ? i % 2 : 0];
    const res = page.evaluate(([n]) => window.__arm(n, 3000), [name]);
    await fire(name);
    const r = await res;
    if (i > 0) out.push(r);
    await sleep(rand(150, 400));
  }
  return out;
}

const samples = {};
await page.mouse.click(640, 40);                           // focus the workload page
samples.key = await run('key', () => page.keyboard.press('F8'));
samples.mouse = await run('mouse', async () => { await page.mouse.down(); await page.mouse.up(); });
await page.keyboard.press('F7');                           // motion mode: white cover + block under the pointer
await page.mouse.move(...PTS.motion.mB);
await sleep(500);
samples.motion = await run('motion', n => page.mouse.move(...PTS.motion[n]));
await page.keyboard.press('F6');

await page.keyboard.press('F9');                           // continuous animation: pacing and stalls
await sleep(2000);
await page.evaluate(() => { window.__pt = []; window.__rec = true; window.__nDec = 0; });
await sleep(15000);
const { presentedTimes, decodedFrames } = await page.evaluate(() => {
  window.__rec = false; return { presentedTimes: window.__pt, decodedFrames: window.__nDec };
});
await page.keyboard.press('F10');
console.log(JSON.stringify({ sink, samples, presentedTimes, decodedFrames }));
await browser.close();
