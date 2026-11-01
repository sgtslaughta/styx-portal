import { describe, expect, it } from "vitest";
import { splitResets } from "../save-settings";

describe("splitResets", () => {
  it("routes values equal to the default to reset, others to patch", () => {
    const settings = [{ key: "A", default: 5 }, { key: "B", default: [{ id: "x" }] }, { key: "C", default: "y" }];
    expect(splitResets({ A: 5, B: [{ id: "x" }] as unknown as string, C: "z" }, settings)).toEqual({ patch: { C: "z" }, resets: ["A", "B"] });
  });
  it("never resets secrets", () => {
    expect(splitResets({ S: "" }, [{ key: "S", default: "", type: "secret" }])).toEqual({ patch: { S: "" }, resets: [] });
  });
});
