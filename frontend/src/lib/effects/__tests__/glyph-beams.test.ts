import { describe, expect, it } from "vitest";
import { beamIntensity, calmFactor } from "../glyph-beams";

describe("beamIntensity", () => {
  it("is periodic (230px) along the 45deg axis", () => {
    const d = 230 * Math.SQRT1_2;
    for (const [x, y, t] of [[10, 20, 0.3], [150, 90, 2.1], [300, 40, 5]] as [number, number, number][]) {
      expect(beamIntensity(x + d, y + d, t)).toBeCloseTo(beamIntensity(x, y, t), 6);
    }
  });
  it("is constant across the beam (perpendicular) direction", () => {
    expect(beamIntensity(100 + 50, 100 - 50, 1)).toBeCloseTo(beamIntensity(100, 100, 1), 6);
  });
  it("peaks near 1 at beam centre", () => {
    // u - t*85 = period/2 -> x=y=115*sqrt(2)/... pick u=115 at t=0
    const x = 115 * Math.SQRT1_2;
    expect(beamIntensity(x, x, 0)).toBeCloseTo(1, 6);
  });
});

describe("calmFactor", () => {
  const r = { cx: 100, cy: 100, rx: 50, ry: 50 };
  it("is 0 (calm, alpha 0) inside the rect ellipse and ramps to 1 outside", () => {
    expect(calmFactor(100, 100, r, 0.62, 1.5)).toBe(0);
    expect(calmFactor(500, 500, r, 0.62, 1.5)).toBe(1);
  });
});
