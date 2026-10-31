import { describe, expect, it } from "vitest";
import { frameDiff, hasMotion, isActive } from "../activity";

const px = (v: number, n = 4) => new Uint8ClampedArray(Array.from({ length: n * 4 }, (_, i) => (i % 4 === 3 ? 255 : v)));

describe("isActive", () => {
  const base = { now: 1_000_000, lastInput: 0, lastMotion: 0, visible: true };
  it("true on recent input", () => expect(isActive({ ...base, lastInput: base.now - 60_000 })).toBe(true));
  it("false on stale input and no motion", () => expect(isActive({ ...base, lastInput: base.now - 6 * 60_000 })).toBe(false));
  it("true on recent motion while visible", () => expect(isActive({ ...base, lastMotion: base.now - 30_000 })).toBe(true));
  it("ignores motion when hidden", () => expect(isActive({ ...base, lastMotion: base.now - 30_000, visible: false })).toBe(false));
  it("false on old motion", () => expect(isActive({ ...base, lastMotion: base.now - 3 * 60_000 })).toBe(false));
});

describe("frameDiff", () => {
  it("0 for identical frames", () => expect(frameDiff(px(100), px(100))).toBe(0));
  it("measures luma difference", () => expect(frameDiff(px(100), px(110))).toBeCloseTo(10, 5));
  it("Infinity on size mismatch", () => expect(frameDiff(px(1, 2), px(1, 4))).toBe(Infinity));
  it("hasMotion respects threshold", () => {
    expect(hasMotion(px(100), px(101))).toBe(false);
    expect(hasMotion(px(100), px(105))).toBe(true);
  });
});
