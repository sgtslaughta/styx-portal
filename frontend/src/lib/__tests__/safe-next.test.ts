import { describe, test, expect } from "vitest";
import { safeNext } from "../safe-next";

describe("safeNext", () => {
  test.each(["/sonarr/", "/w/desk/", "/i/dev/?a=1#x", "/"])("accepts %s", (p) => {
    expect(safeNext(p)).toBe(p);
  });
  test.each([null, "", "//evil.com", "/\\evil.com", "https://evil.com/", "evil.com",
    "javascript:alert(1)", "/a\\b", "/x\r\nSet-Cookie: a=b", " /sonarr/", "/\t/evil.com"])(
    "rejects %s", (p) => {
      expect(safeNext(p)).toBeNull();
    });
});
