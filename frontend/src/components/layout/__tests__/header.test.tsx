import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

// jsdom has no CSS layout, so assert the class that right-aligns the user controls at 390.
describe("Header", () => {
  it("keeps user controls right-aligned when the count chips are hidden on mobile", () => {
    const src = readFileSync("src/components/layout/header.tsx", "utf8");
    expect(src).toContain("flex items-center gap-2 max-sm:ml-auto");
  });
});
