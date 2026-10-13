import { describe, expect, it } from "vitest";
import { frameSrc, isFrameBlocked, parseShellPath, shellPathFor } from "../url";
describe("parseShellPath", () => {
  it("splits slug and inner", () =>
    expect(parseShellPath("/_styx/app/sonarr/series/1", "?q=1", "#x")).toEqual({ slug: "sonarr", inner: "/series/1?q=1#x" }));
  it("root", () => expect(parseShellPath("/_styx/app/sonarr/", "", "")).toEqual({ slug: "sonarr", inner: "/" }));
  it.each(["/_styx/app/sonarr//evil.example", "/_styx/app/sonarr/%2e%2e/api", "/_styx/app/sonarr/a/../../x"])(
    "unsafe inner %s falls back to /", (p) => expect(parseShellPath(p, "", "")?.inner).toBe("/"));
  it("rejects a bad slug", () => expect(parseShellPath("/_styx/app/..%2f/", "", "")).toBeNull());
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
