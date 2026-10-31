// Input-to-photon latency of the live seat stream, one run. Prints raw JSON (latstats.py derives the stats).
//   STYX_USER=U STYX_PASS=P node latency.mjs --url=http://127.0.0.1:18443/ [--n=100]
// Per input (key F8, mouse button, pointer motion) and sample: t0 = performance.now() when the page
// receives THAT input type (capture listener; Firefox's synthetic mousemoves do not start a key sample),
// `dec` = first decoded VideoFrame, `pres` = first frame presented by the <video> sink
// (requestVideoFrameCallback: expectedDisplayTime, else presentationTime, else callback time), whose pixel
// at the target point is the EXPECTED grey. Key and mouse step a square through 4 greys (0/85/170/255), so
// sample k expects grey (k mod 4) and an old or skipped change never matches; motion alternates a black block
// between two far points. Before each sample the previous state is re-read from the video and must hold.
// The page counts every event it received into a bit row; read at the start and end, it gives
// `delivered` vs `sent` (input lost vs detection missed). Points are viewport fractions (workload.html).
// A sample with no match in 3 s is a miss, never a latency.
import { chromium } from 'playwright';

const a = Object.fromEntries(process.argv.slice(2).map(s => s.replace(/^--/, '').split(/=(.*)/s).slice(0, 2)));
const N = Number(a.n || 100), sleep = ms => new Promise(r => setTimeout(r, ms));
const rand = (lo, hi) => lo + Math.random() * (hi - lo);   // 150-400 ms: never locked to the frame clock
const VW = 1280, VH = 720, GREY = [0, 85, 170, 255], TOL = 30, TIMEOUT = 3000;
const PT = { key: [0.05, 0.61], mouse: [0.05, 0.76], mA: [0.70, 0.45], mB: [0.80, 0.75] };   // fractions
const bit = (r, i) => [(1 + 1.6 * i + 0.6) / 100, (86 + 4 * r + 1.5) / 100];

const browser = await chromium.launch();
const ctx = await browser.newContext({
  httpCredentials: { username: process.env.STYX_USER, password: process.env.STYX_PASS },
  viewport: { width: VW, height: VH }, deviceScaleFactor: 2,
});
await ctx.addInitScript(([TOL]) => {
  const px = new OffscreenCanvas(1, 1).getContext('2d', { willReadFrequently: true });
  Object.assign(self, { __A: null, __rec: false, __pt: [], __nPres: 0, __nDec: 0 });
  const luma = (src, w, h, [fx, fy]) => {
    try {
      px.drawImage(src, fx * w, fy * h, 1, 1, 0, 0, 1, 1);
      const d = px.getImageData(0, 0, 1, 1).data;
      return 0.299 * d[0] + 0.587 * d[1] + 0.114 * d[2];
    } catch (e) { return null; }                           // closed frame
  };
  const hit = (A, l) => l !== null && Math.abs(l - A.exp) <= TOL;
  const write = WritableStreamDefaultWriter.prototype.write;
  WritableStreamDefaultWriter.prototype.write = function (chunk) {
    // selkies re-writes its last frame about every 1.2 s when idle: only a new timestamp is a new frame.
    if (chunk instanceof VideoFrame && chunk.timestamp !== self.__lastTs) {
      self.__lastTs = chunk.timestamp; self.__nDec++;
      const A = self.__A;
      if (A && A.t0 !== null && A.dec === null && hit(A, luma(chunk, chunk.displayWidth, chunk.displayHeight, A.pt))) A.dec = performance.now();
    }
    return write.call(this, chunk);
  };
  const src = () => document.getElementById('videoStream') || document.getElementById('videoCanvas');
  const dims = s => [s.videoWidth || s.width, s.videoHeight || s.height];
  const onPresent = (now, md, s) => {
    self.__nPres++;
    const tp = md && md.expectedDisplayTime > 0 ? md.expectedDisplayTime
      : md && md.presentationTime > 0 ? md.presentationTime : now;
    if (self.__rec) self.__pt.push(tp);
    const A = self.__A;
    if (A && A.t0 !== null && A.pres === null && hit(A, luma(s, ...dims(s), A.pt))) { A.pres = tp; A.presCb = now; A.done(); }
  };
  self.__startPresent = () => {                            // 'video' (rVFC) or 'raf' fallback
    const v = document.getElementById('videoStream');
    if (v && v.tagName === 'VIDEO' && v.requestVideoFrameCallback) {
      const cb = (now, md) => { onPresent(now, md, v); v.requestVideoFrameCallback(cb); };
      v.requestVideoFrameCallback(cb);
      return 'video';
    }
    const raf = now => { const s = src(); if (s && dims(s)[0]) onPresent(now, null, s); requestAnimationFrame(raf); };
    requestAnimationFrame(raf);
    return 'raf';
  };
  self.__read = pts => { const s = src(); return pts.map(p => (s && dims(s)[0]) ? luma(s, ...dims(s), p) : null); };
  // Wait until the video shows `prev` at `pt` on two reads in a row (or 300 ms): the last change has settled.
  self.__settle = async (pt, prev) => {
    const t = performance.now(); let ok = 0, last = null;
    while (performance.now() - t < 300) {
      last = self.__read([pt])[0];
      ok = last !== null && Math.abs(last - prev) <= TOL ? ok + 1 : 0;
      if (ok >= 2) return { ok: true, last };
      await new Promise(r => setTimeout(r, 20));
    }
    return { ok: false, last };
  };
  self.__arm = (pt, evType, exp, timeout) => new Promise(res => {
    const A = { pt, evType, exp, t0: null, dec: null, pres: null, presCb: null };
    A.done = () => { clearTimeout(A.to); if (self.__A === A) self.__A = null; res({ t0: A.t0, dec: A.dec, pres: A.pres, presCb: A.presCb }); };
    A.to = setTimeout(A.done, timeout);
    self.__A = A;
  });
  for (const t of ['keydown', 'mousedown', 'mousemove'])    // runs first: registered before selkies'
    addEventListener(t, () => { const A = self.__A; if (A && A.t0 === null && A.evType === t) A.t0 = performance.now(); }, true);
}, [TOL]);
const page = await ctx.newPage();
await page.goto(a.url);
await page.waitForFunction(() => [...document.querySelectorAll('#videoStream, #videoCanvas')]
  .some(e => e.offsetWidth > 0 && getComputedStyle(e).display !== 'none'), null, { timeout: 30000 });
let sink = await page.evaluate(() => window.__startPresent());
await sleep(4000);                                         // first frames + paint-over
if (sink === 'video' && !(await page.evaluate(() => window.__nPres))) {
  sink = 'raf';                                            // video element never presented: sample from rAF
  await page.evaluate(() => { document.getElementById('videoStream').requestVideoFrameCallback = undefined; window.__startPresent(); });
}

const readNow = pts => page.evaluate(p => window.__read(p), pts);
const nearest = l => l === null ? null : GREY.reduce((b, g, i) => Math.abs(g - l) < Math.abs(GREY[b] - l) ? i : b, 0);
async function counters() {                                // events the page has received: key, mouse, motion
  await sleep(1200);
  const l = await readNow([0, 1, 2].flatMap(r => Array.from({ length: 12 }, (_, i) => bit(r, i))));
  return [0, 1, 2].map(r => l.slice(r * 12, r * 12 + 12).reduce((s, v, i) => s + (v > 127 ? 1 << i : 0), 0));
}

// One input type: N+1 samples (the first one settles the state and is not recorded).
async function run(kind, fire) {
  const out = [];
  let idx = 0;                                             // grey index the square is believed to show
  if (kind !== 'motion') idx = nearest((await readNow([PT[kind]]))[0]) ?? 0;
  let fired = 0;
  for (let i = 0, tries = 0; i < N + 1 && tries < 4 * N; tries++) {
    const name = kind === 'motion' ? (i % 2 ? 'mB' : 'mA') : kind;
    const prev = kind === 'motion' ? 255 : GREY[idx], exp = kind === 'motion' ? 0 : GREY[(idx + 1) % 4];
    const st = await page.evaluate(([pt, p]) => window.__settle(pt, p), [PT[name], prev]);
    if (!st.ok && kind !== 'motion' && nearest(st.last) !== null && nearest(st.last) !== idx) {
      idx = nearest(st.last); continue;                       // state differs from what we believed: re-read, retry
    }
    const evType = { key: 'keydown', mouse: 'mousedown', motion: 'mousemove' }[kind];
    const res = page.evaluate(([pt, t, e]) => window.__arm(pt, t, e, 3000), [PT[name], evType, exp]);
    await fire(name); fired++;
    const r = await res;
    const ok = r.pres !== null;
    if (ok && kind !== 'motion') idx = (idx + 1) % 4;
    if (i > 0) out.push({ ...r, hit: ok, settled: st.ok });
    if (!ok) await sleep(600);                              // a late change may still land: let it, then re-read
    if (!ok && kind !== 'motion') idx = nearest((await readNow([PT[kind]]))[0]) ?? idx;
    await sleep(rand(150, 400));
    i++;
  }
  return { out, fired };
}

const samples = {}, sent = {};
const take = async (kind, p) => { const r = await p; samples[kind] = r.out; sent[kind] = r.fired; };
await page.mouse.click(0.5 * VW, 0.05 * VH);               // focus the workload page (its text box: not counted)
await page.keyboard.press('F6');
const c0 = await counters();
await take('key', run('key', () => page.keyboard.press('F8')));
await page.mouse.move(PT.mouse[0] * VW, PT.mouse[1] * VH);  // click the square's centre, pointer already there
await sleep(500);
await take('mouse', run('mouse', async () => { await page.mouse.down(); await sleep(30); await page.mouse.up(); }));
await page.keyboard.press('F7');                           // motion mode: white cover + block under the pointer
await page.mouse.move(0.5 * VW, 0.5 * VH);                 // off-target first, so arriving at mB counts as a move
await page.mouse.move(PT.mB[0] * VW, PT.mB[1] * VH);
await sleep(500);
await take('motion', run('motion', n => page.mouse.move(PT[n][0] * VW, PT[n][1] * VH)));
sent.motion += 1;                                          // the arrival at mB above
await page.keyboard.press('F6');
const c1 = await counters();
const delivered = { key: c1[0] - c0[0], mouse: c1[1] - c0[1], motion: c1[2] - c0[2] };
for (const k of Object.keys(delivered)) delivered[k] = (delivered[k] + 4096) % 4096;

await page.keyboard.press('F9');                           // continuous animation: pacing and stalls
await sleep(2000);
await page.evaluate(() => { window.__pt = []; window.__rec = true; window.__nDec = 0; });
await sleep(15000);
const { presentedTimes, decodedFrames } = await page.evaluate(() => {
  window.__rec = false; return { presentedTimes: window.__pt, decodedFrames: window.__nDec };
});
await page.keyboard.press('F10');
console.log(JSON.stringify({ sink, samples, sent, delivered, presentedTimes, decodedFrames }));
await browser.close();
