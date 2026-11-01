import { describe, expect, it } from "vitest";
import { ditherMask } from "../dither-sun";

describe("ditherMask", () => {
  const W = 400, H = 300, horizon = 126;
  const m = ditherMask(W, H, 1, horizon);
  const cols = Math.ceil(W / 5);
  it("has dots above the horizon and none at or below it", () => {
    let above = 0, below = 0;
    m.forEach((v, i) => { if (!v) return; (Math.floor(i / cols) * 5 < horizon ? above++ : below++); });
    expect(above).toBeGreaterThan(0);
    expect(below).toBe(0);
  });
  it("is deterministic per seed", () => {
    expect(ditherMask(W, H, 1, horizon)).toEqual(m);
  });
});
