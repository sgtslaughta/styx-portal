import { describe, expect, it } from "vitest";
import { frameAncestorsBlock, frameSrc, isFrameBlocked, isFrameLocationForbidden, parseShellPath, shellPathFor } from "../url";
describe("parseShellPath", () => {
  it("splits slug and inner", () =>
    expect(parseShellPath("/_styx/app/sonarr/series/1", "?q=1", "#x")).toEqual({ slug: "sonarr", inner: "/series/1?q=1#x" }));
  it("root", () => expect(parseShellPath("/_styx/app/sonarr/", "", "")).toEqual({ slug: "sonarr", inner: "/" }));
  it.each(["/_styx/app/sonarr//evil.example", "/_styx/app/sonarr/%2e%2e/api", "/_styx/app/sonarr/a/../../x"])(
    "unsafe inner %s falls back to /", (p) => expect(parseShellPath(p, "", "")?.inner).toBe("/"));
  it("rejects a bad slug", () => expect(parseShellPath("/_styx/app/..%2f/", "", "")).toBeNull());
});
describe("frameSrc cookie-root never reaches Styx control paths", () => {
  it.each(["/_styx/exit", "/api/auth/me", "/API/x", "/internal/strip", "/login", "/logout", "/setup",
    "/accept-invite?t=1", "/change-password", "/%61pi/x", "/api;/y", "/_STYX;a/exit"])("%s falls back to /", (inner) =>
    expect(frameSrc("cookie-root", "immich", inner)).toBe("/"));
  it("keeps app paths", () => expect(frameSrc("cookie-root", "immich", "/web/index.html?a=1")).toBe("/web/index.html?a=1"));
  it("path mode keeps the app's own /api and /login (they live under /<slug>)", () => {
    expect(frameSrc("path", "sonarr", "/api/v3/x")).toBe("/sonarr/api/v3/x");
    expect(frameSrc("path", "sonarr", "/login")).toBe("/sonarr/login");
  });
});
it("frameSrc", () => {
  expect(frameSrc("path", "sonarr", "/series")).toBe("/sonarr/series");
  expect(frameSrc("cookie-root", "immich", "/photos")).toBe("/photos");
});
describe("shellPathFor", () => {
  it("path app inside its prefix", () =>
    expect(shellPathFor("path", "sonarr", { pathname: "/sonarr/series", search: "", hash: "" })).toBe("/_styx/app/sonarr/series"));
  it("path app leaving its prefix", () =>
    expect(shellPathFor("path", "sonarr", { pathname: "/radarr/", search: "", hash: "" })).toBeNull());
  it("focus app anywhere except Styx paths", () => {
    expect(shellPathFor("cookie-root", "immich", { pathname: "/photos", search: "?a=1", hash: "" })).toBe("/_styx/app/immich/photos?a=1");
    expect(shellPathFor("cookie-root", "immich", { pathname: "/_styx/exit", search: "", hash: "" })).toBeNull();
  });
});
it("isFrameBlocked", () => {
  expect(isFrameBlocked({ contentWindow: { location: { href: "about:blank" } } })).toBe(true);
  expect(isFrameBlocked({ contentWindow: { get location(): never { throw new DOMException("x", "SecurityError"); } } } as never)).toBe(true);
  expect(isFrameBlocked({ contentWindow: { location: { href: "https://h/sonarr/" } } })).toBe(false);
});

describe("frameAncestorsBlock", () => {
  it.each([
    ["frame-ancestors 'none'", true],
    ["default-src 'self'; frame-ancestors https://other.example", true],
    ["frame-ancestors 'self'", false],
    ["frame-ancestors *", false],
    ["default-src 'self'", false],
    [null, false],
    // Headers.get joins repeated CSP headers with ", "; any one policy can refuse
    ["frame-ancestors 'self', frame-ancestors 'none'", true],
    ["default-src 'self', frame-ancestors 'none'", true],
    ["frame-ancestors 'none', default-src 'self'", true],
    // sources naming Styx's own origin allow it
    ["frame-ancestors https://styx.example", false],
    ["frame-ancestors https://styx.example/", false],
    ["frame-ancestors https:", false],
    ["frame-ancestors styx.example", false],
    ["frame-ancestors https://*.example", false],
    ["frame-ancestors http://styx.example", true],
    ["frame-ancestors https://evilstyx.example", true],
  ])("%s -> %s", (csp, want) => { expect(frameAncestorsBlock(csp, "https://styx.example")).toBe(want); });
});

describe("Styx's own SAMEORIGIN pages are never flagged as blocked", () => {
  // The 503/403/expired pages carry X-Frame-Options SAMEORIGIN and frame-ancestors 'self'.
  const csp = "default-src 'self'; frame-ancestors 'self'; base-uri 'self'";
  it("probe: frame-ancestors 'self' is not a block", () => expect(frameAncestorsBlock(csp, "https://styx.example")).toBe(false));
  it("probe: the old DENY page would have been", () =>
    expect(frameAncestorsBlock("default-src 'self'; frame-ancestors 'none'", "https://styx.example")).toBe(true));
  it("a same-origin error document is readable, so not forbidden", () => {
    const frame = { contentWindow: { location: { href: "https://styx.example/sonarr/" } } };
    expect(isFrameLocationForbidden(frame)).toBe(false);
    expect(isFrameBlocked(frame)).toBe(false);
  });
});
