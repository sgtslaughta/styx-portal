import { readFileSync, readdirSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { TOKENS, TEXT_PAIRS, contrast } from "@/styles/tokens";

describe("Styx tokens", () => {
  it.each(TEXT_PAIRS)("%s on %s ≥ 4.5:1 (%s)", (fg, bg) => {
    expect(contrast(fg, bg)).toBeGreaterThanOrEqual(4.5);
  });
  it("globals.css applies each mode's hexes in its own block", () => {
    const css = readFileSync("src/styles/globals.css", "utf8").toLowerCase();
    const root = /:root\s*\{[^}]*\}/.exec(css)![0];
    const dark = /\.dark\s*\{[^}]*\}/.exec(css)![0];
    for (const hex of Object.values(TOKENS.light)) expect(root).toContain(hex.toLowerCase());
    for (const hex of Object.values(TOKENS.dark)) expect(dark).toContain(hex.toLowerCase());
  });
  it("each mode defines --warning-foreground and a chart-2 distinct from Obol", () => {
    const css = readFileSync("src/styles/globals.css", "utf8").toLowerCase();
    const root = /:root\s*\{[^}]*\}/.exec(css)![0];
    const dark = /\.dark\s*\{[^}]*\}/.exec(css)![0];
    expect(root).toContain(`--warning-foreground: ${TOKENS.light.warningForeground.toLowerCase()}`);
    expect(dark).toContain(`--warning-foreground: ${TOKENS.dark.warningForeground.toLowerCase()}`);
    for (const [blk, bg] of [[root, TOKENS.light.background], [dark, TOKENS.dark.background]] as const) {
      const c2 = /--chart-2:\s*(#[0-9a-f]{6})/.exec(blk)![1]!;
      expect(c2).not.toBe(TOKENS.light.obol.toLowerCase());
      expect(contrast(c2, bg)).toBeGreaterThanOrEqual(3);
    }
  });
  it("light auth form keeps Current primary", () => {
    const css = readFileSync("src/styles/globals.css", "utf8").toLowerCase();
    const form = /(?<!\.dark )\.styx-auth-form\s*\{[^}]*\}/.exec(css)![0];
    expect(form).toContain(TOKENS.light.primary.toLowerCase());
    expect(form).toContain(TOKENS.light.primaryForeground.toLowerCase());
    expect(form).not.toContain(TOKENS.dark.primary.toLowerCase());
  });
});

describe("warning text", () => {
  it("never uses an opacity variant of text-warning-foreground in src", () => {
    const walk = (d: string): string[] => readdirSync(d, { withFileTypes: true }).flatMap((e) =>
      e.isDirectory() ? (e.name === "__tests__" ? [] : walk(`${d}/${e.name}`)) : [`${d}/${e.name}`]);
    const bad = walk("src").filter((f) => /\.(tsx?|css)$/.test(f))
      .filter((f) => /text-warning-foreground\//.test(readFileSync(f, "utf8")));
    expect(bad).toEqual([]);
  });
});
