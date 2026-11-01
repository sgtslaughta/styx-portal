// Hero composite: a 1440x900@2x capture inside a minimal browser frame over the Styx backdrop (2400x1400).
import type { Browser } from "@playwright/test";

export async function composeHero(browser: Browser, png: Buffer, out: string) {
  const p = await browser.newPage({ viewport: { width: 2400, height: 1400 }, deviceScaleFactor: 1 });
  const W = 2000, H = Math.round(W * 0.625) + 56; // app at 1440x900 scaled to 2000 wide + title bar
  await p.setContent(`<!doctype html><meta charset="utf-8"><style>
*{margin:0;box-sizing:border-box}body{width:2400px;height:1400px;overflow:hidden;position:relative;font-family:system-ui,sans-serif;
background:radial-gradient(1500px 900px at 18% 8%,#1e5a73 0,transparent 60%),radial-gradient(1300px 900px at 92% 100%,#173a8a 0,transparent 58%),linear-gradient(160deg,#0f2438,#0b1822 60%,#0a1219)}
body:before{content:"";position:absolute;inset:0;background-image:linear-gradient(rgba(255,255,255,.035) 1px,transparent 1px),linear-gradient(90deg,rgba(255,255,255,.035) 1px,transparent 1px);background-size:64px 64px;
-webkit-mask-image:radial-gradient(ellipse at center,#000 30%,transparent 78%)}
.f{position:absolute;left:${(2400 - W) / 2}px;top:${(1400 - H) / 2}px;width:${W}px;height:${H}px;border-radius:22px;overflow:hidden;background:#0f1c22;
box-shadow:0 60px 140px rgba(0,0,0,.6),0 18px 40px rgba(0,0,0,.4),0 0 0 1px rgba(255,255,255,.12)}
.b{height:56px;background:linear-gradient(#26343c,#1d2a31);display:flex;align-items:center;padding:0 22px;gap:11px;border-bottom:1px solid rgba(0,0,0,.4)}
.b i{width:15px;height:15px;border-radius:50%;background:#ff5f57}.b i:nth-child(2){background:#febc2e}.b i:nth-child(3){background:#28c840}
.b span{margin:0 auto;transform:translateX(-30px);background:#121c21;color:#a9bcc4;font-size:20px;padding:6px 40px;border-radius:12px;min-width:620px;text-align:center}
img{display:block;width:${W}px;height:${H - 56}px}</style>
<div class="f"><div class="b"><i></i><i></i><i></i><span>styx.example.com</span></div><img src="data:image/png;base64,${png.toString("base64")}"></div>`);
  await p.screenshot({ path: out });
  await p.close();
}
