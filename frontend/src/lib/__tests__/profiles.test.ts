import { expect, test } from "vitest";
import { profileMountOf } from "../profiles";

test("explicit profile mount wins", () => {
  expect(profileMountOf("/config", [{ mount: "/data" }])).toBe("/config");
});
test("falls back to first volume mount", () => {
  expect(profileMountOf("", [{ mount: "/data" }, { mount: "/x" }])).toBe("/data");
  expect(profileMountOf(null, [{ mount: "/data" }])).toBe("/data");
});
test("none when no volumes and no mount", () => {
  expect(profileMountOf("  ", [])).toBe("");
  expect(profileMountOf(undefined, undefined)).toBe("");
});
