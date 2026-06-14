import type {
  Instance,
  InstanceCreate,
  InstanceStatus,
  PulledImage,
  RegistryImage,
  ServiceTemplate,
  TemplateCreate,
} from "@/lib/types";

export type Workstation = {
  id: string; name: string; subdomain: string; hostname: string;
  lan_ip: string; port: number; status: string; display_server: string;
  gpu_info: Record<string, unknown>; os_info: Record<string, unknown>;
  agent_version: string; agent_outdated: boolean;
  stream_settings: { encoder: string; framerate: number; bitrate_kbps: number };
  all_users: boolean; last_heartbeat: string | null; last_error: string | null;
  created_at: string; allowed_user_ids: string[];
  in_use: boolean; in_use_by: string | null; in_use_self: boolean;
};
export type EnrollToken = {
  token: string; expires_at: string;
  lan_command: string | null; public_command: string;
  lan_url_source: "env" | "detected" | "none";
};

export type WorkstationUpdateCommand = {
  latest_version: string;
  current_version: string;
  lan_command: string | null;
  public_command: string;
  lan_url_source: "env" | "detected" | "none";
};

export type OAuthProviderRow = {
  id: string; name: string; display_label: string; kind: string;
  issuer_url: string | null; client_id: string; scopes: string;
  role_map: Record<string, unknown>; enabled: boolean; has_secret: boolean;
  icon_url: string | null; trust_email: boolean; allow_signup: boolean;
  auto_promote_admins: boolean; redirect_uri: string; test_redirect_uri: string;
};
export type OAuthProviderCreate = {
  name: string; display_label: string; kind: string; issuer_url?: string;
  authorize_url?: string; token_url?: string; userinfo_url?: string;
  client_id: string; client_secret: string; scopes?: string; role_map?: Record<string, unknown>;
  icon_url?: string | null; trust_email?: boolean; allow_signup?: boolean; auto_promote_admins?: boolean;
};

export type ProviderTestResult = {
  ok: boolean;
  checks: { label: string; ok: boolean; detail: string }[];
};

export type DiagCheck = { key: string; ok: boolean; latency_ms: number; detail: string };
export type Diagnostics = { ok: boolean; checked_at: string; checks: DiagCheck[] };
export type DiagHistory = {
  timestamps: number[];
  status: Record<string, boolean[]>;
  latency_ms: Record<string, number[]>;
};

export type SetupPreflight = {
  docker: { ok: boolean; detail: string };
  deploy_mode: string;
  domain_set: boolean;
  data_writable: boolean;
};

import { singleFlight } from "./single-flight";

const BASE = "/api";

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

function getCookie(name: string): string | null {
  const m = document.cookie.match(new RegExp("(?:^|; )" + name + "=([^;]*)"));
  return m && m[1] ? decodeURIComponent(m[1]) : null;
}

// Spend the long-lived refresh token to mint a fresh access token. Coalesced:
// a burst of polls all hitting 401 at once shares ONE refresh, so we never
// replay a rotated token and trip the backend's RFC 9700 family revocation.
const silentRefresh = singleFlight(async (): Promise<boolean> => {
  const csrf = getCookie("csrf_token");
  const res = await fetch(`${BASE}/auth/refresh`, {
    method: "POST",
    credentials: "include",
    headers: csrf !== null ? { "X-CSRF-Token": csrf } : {},
  });
  return res.ok;
});

async function request<T>(path: string, init?: RequestInit, retried = false): Promise<T> {
  const method = (init?.method ?? "GET").toUpperCase();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(init?.headers as Record<string, string>),
  };
  if (["POST", "PUT", "PATCH", "DELETE"].includes(method)) {
    const csrf = getCookie("csrf_token");
    if (csrf !== null) headers["X-CSRF-Token"] = csrf;
  }
  const res = await fetch(`${BASE}${path}`, {
    credentials: "include",
    ...init,
    headers,
  });
  if (res.status === 401 && !path.startsWith("/auth/")) {
    // Access token expired (e.g. the user was busy in the streaming window and
    // this tab sat idle past the 15-min TTL). Try one silent refresh + retry
    // before giving up — only bounce to /login if the refresh itself fails.
    if (!retried && (await silentRefresh())) {
      return request<T>(path, init, true);
    }
    window.location.href = "/login?expired=1";
    throw new Error("Unauthorized");
  }
  if (!res.ok) {
    const detail = await res.json().catch(() => ({ detail: res.statusText }));
    throw new ApiError(detail.detail || res.statusText, res.status);
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}

export const api = {
  listInstances: () => request<Instance[]>("/instances"),
  screenshotUrl: (id: string) => `${BASE}/instances/${id}/screenshot`,
  refreshScreenshot: (id: string) =>
    request<{ ok: boolean }>(`/instances/${id}/screenshot/refresh`, { method: "POST" }),
  createInstance: (data: InstanceCreate) =>
    request<Instance>("/instances", { method: "POST", body: JSON.stringify(data) }),
  startInstance: (id: string) =>
    request<Instance>(`/instances/${id}/start`, { method: "POST" }),
  stopInstance: (id: string) =>
    request<Instance>(`/instances/${id}/stop`, { method: "POST" }),
  restartInstance: (id: string) =>
    request<Instance>(`/instances/${id}/restart`, { method: "POST" }),
  recreateInstance: (id: string) =>
    request<Instance>(`/instances/${id}/recreate`, { method: "POST" }),
  pauseInstance: (id: string) =>
    request<Instance>(`/instances/${id}/pause`, { method: "POST" }),
  unpauseInstance: (id: string) =>
    request<Instance>(`/instances/${id}/unpause`, { method: "POST" }),
  updateInstance: (id: string, data: { name?: string; env_overrides?: Record<string, string>; session_config?: Record<string, unknown> }) =>
    request<Instance>(`/instances/${id}`, { method: "PATCH", body: JSON.stringify(data) }),
  deleteInstance: (
    id: string,
    removeVolumes = false,
    removeImage = false,
    removeTemplate = false,
  ) =>
    request<void>(
      `/instances/${id}?remove_volumes=${removeVolumes}&remove_image=${removeImage}&remove_template=${removeTemplate}`,
      { method: "DELETE" },
    ),
  getInstanceStatus: (id: string) =>
    request<InstanceStatus>(`/instances/${id}/status`),
  keepalive: (id: string) =>
    request<Instance>(`/instances/${id}/keepalive`, { method: "POST" }),
  getInstanceStats: (id: string) =>
    request<{ cpu_percent: number; memory_mb: number; memory_limit_mb: number; memory_percent: number }>(`/instances/${id}/stats`),

  listTemplates: () => request<ServiceTemplate[]>("/templates"),
  createTemplate: (data: TemplateCreate) =>
    request<ServiceTemplate>("/templates", { method: "POST", body: JSON.stringify(data) }),
  updateTemplate: (id: string, data: Partial<TemplateCreate>) =>
    request<ServiceTemplate>(`/templates/${id}`, { method: "PUT", body: JSON.stringify(data) }),
  deleteTemplate: (id: string) => request<void>(`/templates/${id}`, { method: "DELETE" }),

  listRegistryImages: (params?: { category?: string; search?: string }) => {
    const qs = new URLSearchParams();
    if (params?.category) qs.set("category", params.category);
    if (params?.search) qs.set("search", params.search);
    const q = qs.toString();
    return request<RegistryImage[]>(`/registry/images${q ? `?${q}` : ""}`);
  },
  getRegistryImage: (name: string) => request<RegistryImage>(`/registry/images/${name}`),

  getGpuInfo: () => request<{ available: boolean; type: string | null; devices: string[] }>("/system/gpu"),

  listImages: () => request<PulledImage[]>("/images"),
  deleteImage: (id: string) => request<void>(`/images/${id}`, { method: "DELETE" }),
  purgeImages: () => request<void>("/images", { method: "DELETE" }),

  // System metrics
  getSystemMetrics: () => request<{
    aggregate_cpu: number;
    aggregate_ram_mb: number;
    disk_used_gb: number;
    disk_total_gb: number;
    recent_events: { type: string; instance: string; time: string; details?: string }[];
    host: { docker_version?: string; gpu?: string; network?: string; uptime?: number };
  }>("/system/metrics"),
  getDiagnostics: () => request<Diagnostics>("/system/diagnostics"),
  getDiagnosticsHistory: (range: string) =>
    request<DiagHistory>(`/system/diagnostics/history?range=${range}`),

  getSessionEvents: (instanceId: string) =>
    request<{ type: string; time: string; details?: string }[]>(`/instances/${instanceId}/events`),

  getResourceHistory: (range: string) =>
    request<{
      aggregate_cpu: number[];
      aggregate_ram: number[];
      storage: { volumes_gb: number; images_gb: number; total_gb: number; available_gb: number };
    }>(`/system/metrics/history?range=${range}`),

  getInstanceLogs: (instanceId: string) =>
    request<string[]>(`/instances/${instanceId}/logs`),

  setupRequired: () => request<{ setup_required: boolean }>("/auth/setup-required"),
  setupPreflight: () => request<SetupPreflight>("/auth/setup-preflight"),
  setup: (data: { username: string; email?: string; password: string }) =>
    request<{ id: string; username: string; role: string }>("/auth/setup", {
      method: "POST", body: JSON.stringify(data) }),
  login: (data: { username: string; password: string }) =>
    request<{ id: string; username: string; role: string; must_change_pw?: boolean }>("/auth/login", {
      method: "POST", body: JSON.stringify(data) }),
  logout: (endSession = false) =>
    request<{ ok: boolean }>(
      `/auth/logout${endSession ? "?end_session=true" : ""}`,
      { method: "POST" },
    ),
  refreshSession: () => request<{ ok: boolean }>("/auth/refresh", { method: "POST" }),
  me: () => request<{ id: string; username: string; email: string | null; role: string }>("/auth/me"),
  acceptInvite: (data: { token: string; username: string; password: string }) =>
    request<{ id: string; username: string; role: string }>("/auth/accept-invite", {
      method: "POST", body: JSON.stringify(data) }),
  listUsers: () => request<{ id: string; username: string; email: string | null; role: string; is_active: boolean; last_login: string | null; locked_until: string | null; failed_count: number }[]>("/users"),
  createInvite: (data: { email?: string; role: string }) =>
    request<{ token: string; expires_at: string | null }>("/users/invites", {
      method: "POST", body: JSON.stringify(data) }),
  disableUser: (id: string) => request<unknown>(`/users/${id}/disable`, { method: "PATCH" }),
  changeRole: (id: string, role: string) =>
    request<unknown>(`/users/${id}/role?role=${role}`, { method: "PATCH" }),
  unlockUser: (id: string) => request(`/users/${id}/unlock`, { method: "POST" }),
  resetUserPassword: (id: string) =>
    request<{ temp_password: string }>(`/users/${id}/reset-password`, { method: "POST" }),
  forcePasswordChange: (id: string) =>
    request(`/users/${id}/force-password-change`, { method: "POST" }),
  deleteUser: (id: string) => request(`/users/${id}`, { method: "DELETE" }),
  changePassword: (old_password: string, new_password: string) =>
    request("/auth/change-password", { method: "POST",
      body: JSON.stringify({ old_password, new_password }) }),

  // Workstations
  listWorkstations: () => request<Workstation[]>("/workstations"),
  myWorkstations: () => request<Workstation[]>("/workstations/mine"),
  mintEnrollToken: () =>
    request<EnrollToken>("/workstations/enroll-tokens", { method: "POST" }),
  updateWorkstation: (id: string, data: { name?: string; all_users?: boolean;
    stream_settings?: Record<string, unknown> }) =>
    request<Workstation>(`/workstations/${id}`, { method: "PATCH", body: JSON.stringify(data) }),
  setWorkstationAccess: (id: string, user_ids: string[]) =>
    request<Workstation>(`/workstations/${id}/access`, { method: "PUT", body: JSON.stringify({ user_ids }) }),
  revokeWorkstation: (id: string, purge = false) =>
    request<{ ok: boolean }>(`/workstations/${id}?purge=${purge}`, { method: "DELETE" }),
  workstationConnectUrl: (id: string, force = false) =>
    request<{ url: string }>(`/workstations/${id}/connect${force ? "?force=true" : ""}`),
  workstationUpdateCommand: (id: string) =>
    request<WorkstationUpdateCommand>(`/workstations/${id}/update-command`),

  oauthProviders: () => request<{ name: string; display_label: string; icon_url: string | null }[]>("/auth/oauth/providers"),
  oauthStartUrl: (name: string) => `/api/auth/oauth/${name}/start`,
  linkStartUrl: (name: string) => `/api/auth/link/${name}/start`,
  linkedProviders: () => request<{ provider: string; email: string | null; created_at: string }[]>("/auth/link/providers"),
  unlinkProvider: (name: string) => request<{ ok: boolean }>(`/auth/link/${name}`, { method: "DELETE" }),
  listOAuthProviders: () => request<OAuthProviderRow[]>("/oauth-providers"),
  createOAuthProvider: (data: OAuthProviderCreate) =>
    request<OAuthProviderRow>("/oauth-providers", { method: "POST", body: JSON.stringify(data) }),
  updateOAuthProvider: (id: string, data: Partial<OAuthProviderCreate> & { enabled?: boolean }) =>
    request<OAuthProviderRow>(`/oauth-providers/${id}`, { method: "PATCH", body: JSON.stringify(data) }),
  deleteOAuthProvider: (id: string) => request<void>(`/oauth-providers/${id}`, { method: "DELETE" }),
  testOAuthConfig: (id: string) =>
    request<ProviderTestResult>(`/oauth-providers/${id}/test/config`, { method: "POST" }),
  oauthTestStartUrl: (id: string) => `/api/oauth-providers/${id}/test/start`,

  // System settings
  getSystemSettings: () =>
    request<{ group: string; label: string; settings: {
      key: string; label: string; help: string; type: "int" | "bool" | "rate";
      value: number | boolean | string; default: number | boolean | string;
      min: number | null; max: number | null }[] }[]>("/system-settings"),
  updateSystemSettings: (changes: Record<string, number | boolean | string>) =>
    request("/system-settings", { method: "PATCH", body: JSON.stringify(changes) }),
  resetSystemSetting: (key: string) =>
    request(`/system-settings/${key}/reset`, { method: "POST" }),
};
