// Usage: node run.mjs convert|render <dir> [names...]   (runs inside the playwright container)
import { build } from "esbuild";
import { chromium } from "playwright";
import { readFileSync, writeFileSync, readdirSync } from "node:fs";
import { join, resolve } from "node:path";

const [mode, dir, ...names] = process.argv.slice(2);
const here = import.meta.dirname;
await build({ entryPoints: [join(here, "page.js")], bundle: true, format: "iife", outfile: join(here, "node_modules/.bundle.js"), logLevel: "error", define: { "process.env.NODE_ENV": '"production"' } });
const fonts = resolve(here, "node_modules/@excalidraw/excalidraw/dist/prod/");
const browser = await chromium.launch();
const page = await browser.newPage();
page.on("pageerror", (e) => console.error("pageerror", e.message));
await page.setContent("<html><body></body></html>");
await page.evaluate((p) => { window.EXCALIDRAW_ASSET_PATH = "file://" + p + "/"; }, fonts);
await page.addScriptTag({ path: join(here, "node_modules/.bundle.js") });

const ext = mode === "convert" ? ".mmd" : ".excalidraw";
const all = readdirSync(dir).filter((f) => f.endsWith(ext)).map((f) => f.slice(0, -ext.length));
let fail = 0;
for (const n of names.length ? names : all) {
  try {
    if (mode === "convert") {
      const scene = await page.evaluate((s) => window.convert(s), readFileSync(join(dir, n + ".mmd"), "utf8"));
      writeFileSync(join(dir, n + ".excalidraw"), JSON.stringify(scene, null, 1));
    } else {
      const scene = JSON.parse(readFileSync(join(dir, n + ".excalidraw"), "utf8"));
      for (const [v, dark] of [["light", false], ["dark", true]])
        writeFileSync(join(dir, `${n}-${v}.svg`), await page.evaluate(([s, d]) => window.render(s, d), [scene, dark]));
    }
    console.log("ok", n);
  } catch (e) { fail++; console.error("FAIL", n, e.message); }
}
await browser.close();
process.exit(fail ? 1 : 0);
