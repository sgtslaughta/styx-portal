// Usage: node extract.mjs <repo> <outdir>  -- pulls ```mermaid blocks from README.md and docs/**/*.md
// into <outdir>/<slug>-<n>.mmd and swaps each block for light/dark SVG image links.
import { readFileSync, writeFileSync, readdirSync, statSync, mkdirSync } from "node:fs";
import { join, relative, dirname } from "node:path";

const [repo, out] = process.argv.slice(2);
mkdirSync(out, { recursive: true });
const walk = (d) => readdirSync(d).flatMap((f) => { const p = join(d, f); return statSync(p).isDirectory() ? (f === "superpowers" ? [] : walk(p)) : p.endsWith(".md") ? [p] : []; });
const re = /^```mermaid\n([\s\S]*?)^```\n/gm;
for (const f of [join(repo, "README.md"), ...walk(join(repo, "docs"))]) {
  const rel = relative(repo, f);
  const slug = rel === "README.md" ? "readme" : rel.replace(/^docs\//, "").replace(/\.md$/, "").replace(/\//g, "-");
  let n = 0;
  const src = readFileSync(f, "utf8");
  const text = src.replace(re, (_, body) => {
    n++;
    const name = `${slug}-${n}`;
    writeFileSync(join(out, name + ".mmd"), body);
    const base = relative(dirname(f), out) || ".";
    const alt = `TODO alt ${name}`;
    return rel === "README.md"
      ? `<picture><source media="(prefers-color-scheme: dark)" srcset="${base}/${name}-dark.svg"><img src="${base}/${name}-light.svg" alt="${alt}"></picture>\n`
      : `![${alt}](${base}/${name}-light.svg#only-light)\n![${alt}](${base}/${name}-dark.svg#only-dark)\n`;
  });
  if (n) { writeFileSync(f, text); console.log(rel, n); }
}
