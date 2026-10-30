// Playwright probe: load the isolated gateway, resize the viewport, record
// page reloads, console lines, and when the canvas repaints after the refit.
// Usage: node probe.mjs <label> <outdir>
import { chromium } from 'playwright';
import fs from 'fs';

const [label, out] = process.argv.slice(2);
const t0 = Date.now();
const ev = [];
const note = (k, v = '') => ev.push({ t: Date.now() - t0, k, v: String(v).slice(0, 300), abs: Date.now() });

const browser = await chromium.launch({ args: ['--autoplay-policy=no-user-gesture-required'] });
const ctx = await browser.newContext({
  viewport: { width: 1280, height: 720 },
  httpCredentials: { username: 'u', password: 'p' },
});
const page = await ctx.newPage();
const cdp = await ctx.newCDPSession(page);
const chg = [];   // [epoch ms, size] per composited frame whose pixels changed
cdp.on('Page.screencastFrame', async f => {
  chg.push([Math.round(f.metadata.timestamp * 1000), f.data.length]);
  await cdp.send('Page.screencastFrameAck', { sessionId: f.sessionId }).catch(() => {});
});
await cdp.send('Page.startScreencast', { format: 'jpeg', quality: 10, maxWidth: 320, maxHeight: 180, everyNthFrame: 1 });
page.on('console', m => note('console', m.text()));
page.on('load', () => note('load'));
page.on('framenavigated', f => f === page.mainFrame() && note('nav', f.url()));
page.on('worker', w => note('worker', w.url().slice(0, 60)));

// sample the biggest canvas: size + a cheap content hash, every 100 ms
async function sample() {
  return page.evaluate(() => {
    const cs = [...document.querySelectorAll('canvas, video')];
    if (!cs.length) return null;
    const c = cs.sort((a, b) => b.width * b.height - a.width * a.height)[0];
    return `${c.tagName}${c.width}x${c.height}`;
  }).catch(e => 'ERR');
}
async function shot() {
  const b = await page.screenshot({ clip: { x: 40, y: 40, width: 420, height: 420 } }).catch(() => null);
  if (!b) return 'none';
  let h = 0; for (let i = 0; i < b.length; i += 97) h = (h * 31 + b[i]) | 0;
  return h;
}

await page.goto('http://127.0.0.1:8445/');
note('goto-done');
const watch = async (ms, tag) => {
  let last = '', lastShot = '';
  const end = Date.now() + ms;
  while (Date.now() < end) {
    const s = await sample(); const h = await shot();
    if (s !== last) { note(`${tag}:canvas`, s); last = s; }
    if (h !== lastShot) { note(`${tag}:paint`, h); lastShot = h; }
    const dt = Date.now() - (globalThis.rzAt || 1e15);
    if (tag === 'post' && dt > 650 && dt < 2000) await page.screenshot({ path: `${out}/${label}-f${String(dt).padStart(4, '0')}.jpg`, quality: 40, type: 'jpeg' });
    await page.waitForTimeout(100);
  }
};
await watch(12000, 'pre');
note('RESIZE', '1600x900'); globalThis.rzAt = Date.now();
await page.setViewportSize({ width: 1600, height: 900 });
await watch(15000, 'post');
await page.screenshot({ path: `${out}/${label}-end.png` });
fs.writeFileSync(`${out}/${label}.json`, JSON.stringify({ ev, chg, t0 }, null, 1));
await browser.close();
