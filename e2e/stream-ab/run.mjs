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
const page = await ctx.newPage();
await page.goto(a.url);
// selkies draws to <video id=videoStream> or a canvas depending on the sink: wait for whichever shows.
await page.waitForFunction(() => [...document.querySelectorAll('#videoStream, #videoCanvas')]
  .some(e => e.offsetWidth > 0 && getComputedStyle(e).display !== 'none'), null, { timeout: 30000 });
mark('page');
await sleep(4000);                          // first frames + paint-over
mark('ready');

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

const cx = 640, cy = 400;
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

await page.keyboard.press('F9');            // animation on
await sleep(20000);
await page.keyboard.press('F9');
mark('anim');
await sleep(5000);
const sharpEnd = await sharpness();
mark('end');

console.log(JSON.stringify({ marks, sharpStill, sharpAfterScroll, sharpEnd }));
await browser.close();
