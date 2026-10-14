import type { ProxiedService, ServiceTile } from "@/api/client";

/** Admins receive the full model (health_status); members get tiles (up). */
export function toTile(s: ServiceTile | ProxiedService): ServiceTile {
  if (!("health_status" in s)) return s;
  const up = s.health_status === "healthy" ? true : s.health_status === "unhealthy" ? false : null;
  return {
    id: s.id, slug: s.slug, name: s.name, icon: s.icon, mount_mode: s.mount_mode,
    enabled: s.enabled, up, frame_ok: s.frame_ok, needs_setup: s.needs_setup,
  };
}

export const HEALTH = (up: boolean | null) =>
  up === true ? { dot: "bg-success", label: "Healthy" }
    : up === false ? { dot: "bg-transparent ring-2 ring-inset ring-destructive", label: "Unreachable" }
    : { dot: "bg-transparent ring-1 ring-inset ring-muted-foreground", label: "Status unknown" };

/** Where a tile opens. Focus apps always go through /_styx/open (sets the cookie, then redirects). */
export function shellHref(t: ServiceTile): string {
  if (t.mount_mode === "cookie-root") return `/_styx/open/${t.slug}`;
  return t.frame_ok ? `/_styx/app/${t.slug}/` : `/${t.slug}/`;
}
