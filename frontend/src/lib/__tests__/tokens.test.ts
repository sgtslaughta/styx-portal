import { readFileSync } from "node:fs";
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
  it("light auth form keeps Current primary", () => {
    const css = readFileSync("src/styles/globals.css", "utf8").toLowerCase();
    const form = /(?<!\.dark )\.styx-auth-form\s*\{[^}]*\}/.exec(css)![0];
    expect(form).toContain(TOKENS.light.primary.toLowerCase());
    expect(form).toContain(TOKENS.light.primaryForeground.toLowerCase());
    expect(form).not.toContain(TOKENS.dark.primary.toLowerCase());
  });
});
