import { describe, expect, it } from "vitest";
import { shellHref, toTile } from "../service-tiles";
import type { ServiceTile } from "@/api/client";

const t = (o: Partial<ServiceTile> = {}): ServiceTile => ({
  id: "1", slug: "sonarr", name: "Sonarr", icon: null, mount_mode: "path",
  enabled: true, up: true, frame_ok: true, ...o,
});
describe("shellHref", () => {
  it("opens in the shell by default", () => expect(shellHref(t())).toBe("/_styx/app/sonarr/"));
  it("bare path app without overlay", () => expect(shellHref(t({ frame_ok: false }))).toBe("/sonarr/"));
  it("bare focus app without overlay", () =>
    expect(shellHref(t({ mount_mode: "cookie-root", frame_ok: false }))).toBe("/_styx/open/sonarr"));
  it("focus app in shell goes through open", () =>
    expect(shellHref(t({ mount_mode: "cookie-root" }))).toBe("/_styx/open/sonarr"));
});
describe("toTile", () => {
  it("maps admin rows", () =>
    expect(toTile({ ...t(), health_status: "unhealthy" } as never).up).toBe(false));
  it("keeps frame_ok", () =>
    expect(toTile({ ...t(), frame_ok: false, health_status: "healthy" } as never).frame_ok).toBe(false));
});
