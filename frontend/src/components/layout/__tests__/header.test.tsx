import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

// jsdom has no layout: assert the source keeps the user cluster right-aligned and the chips gone.
describe("Header", () => {
  it("has no instance count chips; account menu and theme toggle sit right", () => {
    const src = readFileSync("src/components/layout/header.tsx", "utf8");
    expect(src).not.toContain("CountChip");
    expect(src).not.toContain("useInstances");
    expect(src).toContain('className="ml-auto flex items-center gap-2"');
  });
});
