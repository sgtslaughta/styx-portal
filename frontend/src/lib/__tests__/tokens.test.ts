import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { TOKENS, TEXT_PAIRS, contrast } from "@/styles/tokens";

describe("Styx tokens", () => {
  it.each(TEXT_PAIRS)("%s on %s ≥ 4.5:1 (%s)", (fg, bg) => {
    expect(contrast(fg, bg)).toBeGreaterThanOrEqual(4.5);
  });
  it("globals.css uses the token hexes", () => {
    const css = readFileSync("src/styles/globals.css", "utf8").toLowerCase();
    for (const hex of [...Object.values(TOKENS.light), ...Object.values(TOKENS.dark)]) {
      expect(css).toContain(hex.toLowerCase());
    }
  });
});
