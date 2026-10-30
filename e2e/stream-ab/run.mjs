// Headless controller for one A/B run: opens the real selkies page through
// netem.py, drives a scripted workload over the stream, prints JSON metrics.
//   STYX_USER=U STYX_PASS=P node run.mjs --url=http://127.0.0.1:18443/ [--refuse=av01]
// ponytail: client metrics are coarse (first frame, sharpness of screenshots);
// the server log carries the rest (ab.py).
import { chromium } from 'playwright';

const a = Object.fromEntries(process.argv.slice(2).map(s => s.replace(/^--/, '').split(/=(.*)/s).slice(0, 2)));
const sleep = ms => new Promise(r => setTimeout(r, ms));
const t0 = Date.now(), marks = [];
const mark = name => marks.push([name, (Date.now() - t0) / 1000]);
const cx = 640, cy = 400;

const browser = await chromium.launch();
const ctx = await browser.newContext({
  httpCredentials: { username: process.env.STYX_USER, password: process.env.STYX_PASS },
  viewport: { width: 1280, height: 720 }, deviceScaleFactor: 2,
});
if (a.refuse) {
  // A browser that cannot decode `refuse` (e.g. av01): selkies should step down its encoder list.
  await ctx.addInitScript(codec => {
    if (!self.VideoDecoder) return;
    const orig = VideoDecoder.isConfigSupported.bind(VideoDecoder);
    VideoDecoder.isConfigSupported = c => String(c.codec).startsWith(codec)
      ? Promise.resolve({ supported: false, config: c }) : orig(c);
  }, a.refuse);
}
await ctx.addInitScript(() => {
  const W = self.WritableStreamDefaultWriter;
  if (!W || !self.VideoFrame) return;
  const px = new OffscreenCanvas(1, 1).getContext('2d', { willReadFrequently: true });
  self.__frames = []; self.__luma = -1;
  const write = W.prototype.write;
  W.prototype.write = function (chunk) {
    if (chunk instanceof VideoFrame) {
      self.__frames.push(performance.now());
      try {
        px.drawImage(chunk, 200, 500, 1, 1, 0, 0, 1, 1);
        const d = px.getImageData(0, 0, 1, 1).data;
        self.__luma = 0.299 * d[0] + 0.587 * d[1] + 0.114 * d[2];
      } catch (e) { /* closed frame */ }
    }
    return write.call(this, chunk);
  };
});
const page = await ctx.newPage();
await page.goto(a.url);
// selkies draws to <video id=videoStream> or a canvas depending on the sink: wait for whichever shows.
await page.waitForFunction(() => [...document.querySelectorAll('#videoStream, #videoCanvas')]
  .some(e => e.offsetWidth > 0 && getComputedStyle(e).display !== 'none'), null, { timeout: 30000 });
mark('page');
// Frame monitor at the source: selkies writes each decoded VideoFrame to a
// MediaStreamTrackGenerator; time every write and read the F8 square's luma from
// the frame itself (workload.html #flip: CSS 0..200 x 150..350 -> stream px
// 0..400 x 300..700 at scale 2). Independent of headless rendering.
await page.evaluate(() => {
  window.__waitFlip = (from, timeout) => new Promise(res => {
    const t0 = performance.now();
    const poll = () => {
      if (Math.abs(window.__luma - from) > 80) return res(performance.now() - t0);
      if (performance.now() - t0 > timeout) return res(null);
      setTimeout(poll, 2);
    };
    poll();
  });
});
await sleep(4000);                          // first frames + paint-over
mark('ready');

async function latency(n) {                 // key -> first frame showing the flip, ms
  await page.mouse.click(cx, 40);           // focus the workload page
  const out = [];
  for (let i = 0; i < n; i++) {
    const from = await page.evaluate(() => window.__luma);
    const wait = page.evaluate(([f]) => window.__waitFlip(f, 3000), [from]);
    await page.keyboard.press('F8');
    out.push(await wait);
    await sleep(400);
  }
  const ok = out.filter(v => v !== null).sort((a, b) => a - b);
  const q = p => ok.length ? Math.round(ok[Math.min(ok.length - 1, Math.floor(p * ok.length))]) : null;
  return { latP50: q(0.5), latP95: q(0.95), latMissed: out.length - ok.length };
}

function gaps() {                           // frame gaps over the run
  return page.evaluate(() => {
    const f = window.__frames, g = [];
    for (let i = 1; i < f.length; i++) g.push(f[i] - f[i - 1]);
    const long = g.map((v, i) => [Math.round(f[i] / 1000), Math.round(v)]).filter(([, v]) => v > 500);
    return { frames: f.length, maxGapMs: Math.round(Math.max(0, ...g)), gapsOver500: long.slice(0, 10) };
  });
}

if (a.mode === 'recovery') {                // outage profiles: steady motion, measure the hole
  await page.mouse.click(cx, 40);
  await page.keyboard.press('F9');
  await sleep(Number(a.seconds || 90) * 1000);
  await page.keyboard.press('F9');
  mark('end');
  console.log(JSON.stringify({ marks, ...(await gaps()), ...(await latency(5)) }));
  await browser.close();
  process.exit(0);
}

// Sharpness: variance of the Laplacian over a screenshot's grey levels (higher = crisper text).
async function sharpness() {
  const png = (await page.screenshot({ clip: { x: 340, y: 160, width: 600, height: 400 } })).toString('base64');
  return page.evaluate(async b64 => {
    const img = new Image(); img.src = 'data:image/png;base64,' + b64; await img.decode();
    const c = new OffscreenCanvas(img.width, img.height), g = c.getContext('2d');
    g.drawImage(img, 0, 0);
    const { data, width: w, height: h } = g.getImageData(0, 0, img.width, img.height);
    const y = (i) => 0.299 * data[i] + 0.587 * data[i + 1] + 0.114 * data[i + 2];
    let n = 0, s = 0, s2 = 0;
    for (let r = 1; r < h - 1; r++) for (let q = 1; q < w - 1; q++) {
      const i = (r * w + q) * 4;
      const v = 4 * y(i) - y(i - 4) - y(i + 4) - y(i - 4 * w) - y(i + 4 * w);
      n++; s += v; s2 += v * v;
    }
    return s2 / n - (s / n) ** 2;
  }, png);
}


await page.mouse.move(cx, cy);
await sleep(8000); mark('still');
const sharpStill = await sharpness();

for (let i = 0; i < 300; i++) {             // 30 s of two-way scrolling
  await page.mouse.wheel(0, (Math.floor(i / 50) % 2 ? -1 : 1) * 240);
  await sleep(100);
}
mark('scroll');
await sleep(3000);
const sharpAfterScroll = await sharpness();

await page.mouse.click(cx, 40);             // the workload's text box
await page.keyboard.type('the quick brown fox jumps over the lazy dog 0123456789 '.repeat(6), { delay: 60 });
mark('type');

const lat = await latency(15);
mark('latency');

await page.keyboard.press('F9');            // animation on
await sleep(20000);
await page.keyboard.press('F9');
mark('anim');
await sleep(5000);
const sharpEnd = await sharpness();
mark('end');

// Frame gaps only mean something under steady motion (recovery mode): a still screen sends none.
console.log(JSON.stringify({ marks, sharpStill, sharpAfterScroll, sharpEnd, ...lat }));
await browser.close();
