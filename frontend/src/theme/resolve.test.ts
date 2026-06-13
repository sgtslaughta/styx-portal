import { describe, it, expect } from "vitest";
import { isPublicPath, resolveDark } from "./resolve.ts";

describe("isPublicPath", () => {
  it("matches public routes and their children", () => {
    expect(isPublicPath("/login")).toBe(true);
    expect(isPublicPath("/setup")).toBe(true);
    expect(isPublicPath("/accept-invite/abc123")).toBe(true);
    expect(isPublicPath("/")).toBe(false);
    expect(isPublicPath("/instances")).toBe(false);
    // must not match a path that merely starts with the same letters
    expect(isPublicPath("/loginsomething")).toBe(false);
  });
});

describe("resolveDark", () => {
  it("THE BUG: public page with stored 'dark' follows a LIGHT OS, not the stored pref", () => {
    expect(resolveDark("/login", "dark", false)).toBe(false);
  });

  it("public page follows the OS in both directions, ignoring stored pref", () => {
    expect(resolveDark("/login", "dark", true)).toBe(true); // OS dark -> dark
    expect(resolveDark("/login", "light", true)).toBe(true); // stored light ignored, OS dark
    expect(resolveDark("/setup", "light", false)).toBe(false);
  });

  it("authenticated pages honour the stored preference", () => {
    expect(resolveDark("/", "dark", false)).toBe(true); // stored dark wins on light OS
    expect(resolveDark("/instances", "light", true)).toBe(false); // stored light wins on dark OS
    expect(resolveDark("/", "system", true)).toBe(true); // system -> follows OS
    expect(resolveDark("/", null, false)).toBe(false); // no pref -> system -> light OS
  });
});
