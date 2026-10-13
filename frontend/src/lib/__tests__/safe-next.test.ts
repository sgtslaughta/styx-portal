import { describe, test, expect } from "vitest";
import { safeNext } from "../safe-next";

describe("safeNext", () => {
  test.each(["/sonarr/", "/w/desk/", "/i/dev/?a=1#x", "/", "/i/dev/p/web/", "/instances",
    "/sonarr/?q=a%2Fb", "/apis/x", "/loginx", "/dash?next=/api/x"])("accepts %s", (p) => {
    expect(safeNext(p)).toBe(p);
  });
  test.each([null, "", "//evil.com", "/\\evil.com", "https://evil.com/", "evil.com",
    "javascript:alert(1)", "/a\\b", "/x\r\nSet-Cookie: a=b", " /sonarr/", "/\t/evil.com"])(
    "rejects %s", (p) => {
      expect(safeNext(p)).toBeNull();
    });
  // A cross-site /login?next=… turns into a same-site navigation that carries
  // SameSite=Strict cookies: never follow it into Styx's own control paths.
  test.each(["/api", "/api/", "/api/auth/logout", "/API/auth/logout", "/Api/x?y=1",
    "/internal/strip", "/_styx/exit", "/login", "/login?next=/x", "/LOGIN", "/logout",
    "/setup", "/accept-invite?t=1", "/change-password"])("rejects Styx path %s", (p) => {
    expect(safeNext(p)).toBeNull();
  });
  test.each(["/%61pi/x", "/%2e%2e/api", "/x/%2E%2E/api", "/x%2fapi", "/x%2Fy", "/x%5cy",
    "/x%5C", "/%252e%252e/api", "/./api", "/x/../api", "/a/./b", "/%E0%A4%A"])(
    "rejects encoded/dot path %s", (p) => {
      expect(safeNext(p)).toBeNull();
    });
});
