import { MotionGlobalConfig } from "framer-motion";
import { afterEach, describe, expect, it, vi } from "vitest";
import { applyReducedMotion } from "./motion";

function mockMedia(matches: boolean) {
  vi.stubGlobal("matchMedia", vi.fn().mockReturnValue({ matches }));
}

describe("applyReducedMotion", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    MotionGlobalConfig.skipAnimations = false;
  });
  it("skips all animations (opacity fades included) when the user prefers reduced motion", () => {
    mockMedia(true);
    applyReducedMotion();
    expect(MotionGlobalConfig.skipAnimations).toBe(true);
  });
  it("leaves animations on otherwise", () => {
    mockMedia(false);
    applyReducedMotion();
    expect(MotionGlobalConfig.skipAnimations).toBe(false);
  });
});
