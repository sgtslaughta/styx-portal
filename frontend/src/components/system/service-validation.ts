import type { ProxiedServiceInput } from "@/api/client";

// Mirrors backend/app/schemas_services.py
const SLUG_RE = /^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$/;
const RESERVED = new Set([
  "api", "i", "w", "assets", "login", "setup", "connecting", "change-password", "accept-invite", "_styx",
  "if", "application", "outpost.goauthentik.io", "static", "media", "flows", "ws", "-", ".well-known", "source",
]);
const CONTAINER_RE = /^[a-zA-Z0-9][a-zA-Z0-9_.-]*$/;
const IP_RE = /^(\d+(\.\d+){3}|\[.*\])$/;   // IPv4 or bracketed IPv6 host
const PROXY_IP_ERROR = "A reverse proxy picks the site by hostname, so the upstream address must use one (e.g. https://unraid.home.lan).";
const URL_RE = /^https?:\/\/[^\s/@]+(\/\S*)?$/;

export type FieldErrors = Record<string, string>;
export const BYPASS_PREFIX_ERROR = "Required; must start with /";

export function validateService(f: ProxiedServiceInput, isEdit: boolean): FieldErrors {
  const e: FieldErrors = {};
  if (!isEdit) {
    if (!f.slug.trim()) e.slug = "Slug is required";
    else if (RESERVED.has(f.slug)) e.slug = `"${f.slug}" is reserved`;
    else if (!SLUG_RE.test(f.slug)) e.slug = "Use lowercase letters, digits and hyphens (1-63 chars, no leading/trailing hyphen)";
  }
  if (!f.name.trim()) e.name = "Name is required";
  else if (f.name.length > 255) e.name = "Max 255 characters";
  if (f.kind === "url") {
    const u = f.upstream_url?.trim() ?? "";
    if (!u) e.upstream_url = "Upstream URL is required";
    else if (!URL_RE.test(u) || /[\x00-\x20\x7f]/.test(u)) e.upstream_url = "Use http(s)://host[:port][/path], no credentials";
    else if (f.upstream_is_proxy && IP_RE.test(new URL(u).hostname)) e.upstream_is_proxy = PROXY_IP_ERROR;
  } else {
    if (!f.container) e.container = "Choose or enter a container";
    else if (!CONTAINER_RE.test(f.container)) e.container = "Letters, digits, _ . - only; must start with a letter or digit";
    const p = f.container_port;
    if (p == null) e.container_port = "Port is required";
    else if (!Number.isInteger(p) || p < 1 || p > 65535) e.container_port = "Port must be between 1 and 65535";
  }
  if (f.health_path && !f.health_path.startsWith("/")) e.health_path = "Must start with /";
  if (f.auth_mode === "sso-with-bypass") {
    f.bypass_rules.forEach((r, i) => {
      if (!r.path_prefix.startsWith("/") || r.path_prefix.length > 255) e[`bypass_${i}`] = BYPASS_PREFIX_ERROR;
      else if ((r.required_header?.length ?? 0) > 64) e[`bypass_header_${i}`] = "Max 64 characters";
    });
  }
  return e;
}

type ErrLike = { status?: number; detail?: unknown; message?: string };

/** Map an API failure onto form fields; `rest` is whatever could not be attached to a field. */
export function serverFieldErrors(err: unknown): { fields: FieldErrors; rest: string[] } {
  const { status, detail, message } = (err ?? {}) as ErrLike;
  const fields: FieldErrors = {};
  const rest: string[] = [];
  if (Array.isArray(detail)) {
    for (const d of detail as { loc?: unknown[]; msg?: string }[]) {
      const msg = (d.msg ?? "Invalid value").replace(/^Value error, /, "");
      const field = d.loc && d.loc.length > 1 ? String(d.loc[d.loc.length - 1]) : null;
      if (field && typeof d.loc?.[d.loc.length - 1] === "string") fields[field] = msg;
      else rest.push(msg);
    }
  } else if (status === 409 && typeof detail === "string") fields.slug = detail;
  else if (status === 400 && typeof detail === "string" && /container/i.test(detail)) fields.container = detail;
  else rest.push(message || "Request failed");
  return { fields, rest };
}
