import { chromium } from "playwright";
import { readFileSync } from "fs";
const b = await chromium.launch(); const p = await b.newPage();
for (const n of process.argv.slice(2)) {
  const svg = readFileSync(`/src/docs/assets/diagrams/${n}.svg`, "utf8");
  await p.setContent(`<body style="margin:0;display:inline-block;background:${n.endsWith("-dark") ? "#0d1117" : "#fff"}">${svg}</body>`, { waitUntil: "domcontentloaded" });
  await p.waitForTimeout(800);
  await p.locator("svg").first().screenshot({ path: `/out/${n}.png` });
}
await b.close();
