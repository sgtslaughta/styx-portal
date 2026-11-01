import type {
  Instance,
  InstanceCreate,
  InstanceStatus,
  PulledImage,
  RegistryImage,
  ServiceTemplate,
  TemplateCreate,
} from "@/lib/types";
import { safeNext } from "@/lib/safe-next";

export type Workstation = {
  id: string; name: string; subdomain: string; hostname: string;
  lan_ip: string; port: number; status: string; display_server: string;
  gpu_info: Record<string, unknown>; os_info: Record<string, unknown>;
  agent_version: string; agent_outdated: boolean;
  update_state?: string; update_error?: string | null; update_target?: string;
  stream_settings: Record<string, unknown> & { encoder?: string; framerate?: number; bitrate_kbps?: number };
  all_users: boolean; last_heartbeat: string | null; last_error: string | null;
  created_at: string; allowed_user_ids: string[];
  in_use: boolean; in_use_by: string | null; in_use_self: boolean;
  icon_kind: "auto" | "emoji" | "image"; icon_etag: string;
};
export type BypassRule = {
  path_prefix: string; required_header: string | null;
  header_prefix?: string | null; required_query?: string | null;
};
export type ProxiedService = {
  id: string; slug: string; name: string;
  /** Server-owned: bytes are served by /api/services/{id}/icon?v=icon_etag. */
  icon_kind: "auto" | "emoji" | "image"; icon_etag: string;
  kind: "url" | "docker-local";
  upstream_url: string | null; container: string | null; container_port: number | null;
  upstream_fallback: string | null;
  mount_mode: "path" | "cookie-root";
  auth_mode: "sso" | "sso-with-bypass" | "app-native";
  bypass_rules: BypassRule[]; allowed_groups: string[];
  verify_tls: boolean; health_path: string | null;
  /** url kind: Host/SNI sent to a name-based reverse-proxy upstream (NPM, Caddy). */
  upstream_is_proxy?: boolean;
  health_status: "healthy" | "unhealthy" | "unknown"; health_checked_at: string | null;
  preset_id: string | null; enabled: boolean; created_at: string; updated_at: string;
  /** Server-owned: true when Styx manages the app's mount config. Never sent on write. */
  mount_managed: boolean; needs_setup: boolean; pass_identity: boolean; frame_ok: boolean;
};
/** Non-admin view of GET /services. `up` null = unknown. Admins receive the full ProxiedService instead. */
export type ServiceTile = {
  id: string; slug: string; name: string; icon_kind: ProxiedService["icon_kind"]; icon_etag: string;
  mount_mode: ProxiedService["mount_mode"]; enabled: boolean; up: boolean | null; frame_ok: boolean;
  needs_setup: boolean;
};
/** `icon` is only for create (a preset emoji); omit it on update, icons change via setServiceIcon. */
export type ProxiedServiceInput = Omit<ProxiedService,
  "icon_kind" | "icon_etag" | "id" | "upstream_fallback" | "health_status" | "health_checked_at" | "created_at" | "updated_at" | "mount_managed" | "needs_setup"> & { icon?: string | null };
export type ServicePreset = {
  id: string; name: string; icon: string | null; default_port: number | null;
  mount_mode: ProxiedService["mount_mode"]; auth_mode: ProxiedService["auth_mode"];
  bypass_rules: BypassRule[]; health_path: string | null; verify_tls: boolean;
  base_url_hint: string | null; warnings: string[];
  subpath: { methods: unknown[]; verify_path?: string } | null;
};
export type DiscoveredContainer = {
  name: string; image: string; ports: number[]; networks: string[]; suggested_preset: string | null;
};
export type OpenMode = "new_tab" | "same_tab";
export type Me = { id: string; username: string; email: string | null; role: string;
  open_workspaces: OpenMode | null; open_apps: OpenMode | null; must_change_pw?: boolean; can_use_gpu?: boolean };
export type Group = { id: string; name: string; description: string | null; member_count: number; allow_gpu: boolean };
export type Profile = { template_id: string; template_name: string; display_name: string; volume_name: string; in_use: boolean };

export type MountChange = { target: string; key: string; old: string | null; new: string; created?: boolean };
export type MountPlan = {
  method: "config_file" | null; changes: MountChange[]; needs_consent: boolean; reason: string | null; retry?: boolean; manual?: boolean;
};
export type JobStep = {
  id: string; label: string;
  state: "pending" | "active" | "done" | "failed" | "skipped"; detail: string | null;
};
export type MountJob = {
  id: string; state: "pending" | "running" | "done" | "rolled_back" | "failed";
  steps: JobStep[]; changes: MountChange[]; backup_dir: string | null;
  /** True once a write to the app's settings may have landed (false: nothing was touched). */
  changed: boolean;
  log_excerpt: string | null; created_at: string; finished_at: string | null;
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
  runtime?: "docker" | "kubernetes";
  deploy_mode: string;
  domain_set: boolean;
  data_writable: boolean;
};

import { singleFlight } from "./single-flight";

export type SettingValue = number | boolean | string | null;
export type Setting = {
  key: string;
  label: string;
  help: string;
  type: "int" | "bool" | "rate" | "secret" | "enum" | "str";
  value: SettingValue;
  default: SettingValue;
  min: number | null;
  max: number | null;
  /** secret rows only: plaintext is never returned */
  is_set?: boolean;
  choices?: string[];
};
export type SettingGroup = { group: string; label: string; settings: Setting[] };
export type TurnCheckStatus = "ok" | "warn" | "error" | "skip";
export type TurnCheckItem = { id: string; label: string; status: TurnCheckStatus; detail: string };
export type TurnCheck = { provider: string; checked_at: string; checks: TurnCheckItem[] };
export type TurnUsage = {
  month: string;
  free_gb: number;
  usd_per_gb: number | string;
  total_bytes: number;
  est_usd: number;
  projected_bytes: number;
  projected_usd: number;
  by_workstation: { id: string; name: string; bytes: number }[];
  by_user: { id: string; username: string; bytes: number }[];
  budget_gb?: number;
  over_budget?: boolean;
  cf_egress_bytes?: number | null;
  cf_error?: string | null;
};

const BASE = "/api";

export type LoginResult = {
  id: string; username: string; role: string; must_change_pw?: boolean;
  mfa_required?: boolean; challenge?: string[];
};

export class ApiError extends Error {
  status: number;
  /** Raw `detail` from the response (string, or FastAPI's 422 list). */
  detail?: unknown;
  constructor(message: string, status: number, detail?: unknown) {
    super(message);
    this.status = status;
    this.detail = detail;
  }
}

/** Retry transient failures (429 / 5xx / network) so a rate-limit burst never
 *  looks like a logout. Auth errors (401/403) and other 4xx fail at once. */
export async function withRetry<T>(fn: () => Promise<T>, delays = [1000, 2000, 4000, 8000, 16000]): Promise<T> {
  for (let i = 0; ; i++) {
    try {
      return await fn();
    } catch (e) {
      const transient = !(e instanceof ApiError) || e.status === 429 || e.status >= 500;
      if (!transient || i >= delays.length) throw e;
      await new Promise((r) => setTimeout(r, delays[i]));
    }
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
    // X-Styx-Client: in Focus mode /api belongs to the app without it.
    headers: { "X-Styx-Client": "1", ...(csrf !== null ? { "X-CSRF-Token": csrf } : {}) },
  });
  return res.ok;
});

async function request<T>(path: string, init?: RequestInit, retried = false): Promise<T> {
  const method = (init?.method ?? "GET").toUpperCase();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    "X-Styx-Client": "1",
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
    window.location.href = expiredLoginUrl(window.location.pathname, window.location.search);
    throw new Error("Unauthorized");
  }
  if (!res.ok) {
    const detail = await res.json().catch(() => ({ detail: res.statusText }));
    const d = detail.detail;
    const msg = Array.isArray(d)
      ? d.map((x: { msg?: string }) => x?.msg ?? "invalid").join("; ")
      : d || res.statusText;
    throw new ApiError(msg, res.status, d);
  }
  if (res.status === 204) return undefined as T;
  const text = await res.text();
  return (text ? JSON.parse(text) : undefined) as T;
}

/** /login URL after a 401. Inside the shell (/_styx/app/...) it carries the shell path so sign-in
 * returns there, and goes via /_styx/exit: in Focus mode /login is the app's, and the shell-wrap
 * redirect would send it straight back here (reload loop). */
export function expiredLoginUrl(pathname: string, search: string): string {
  if (!pathname.startsWith("/_styx/app/")) return "/login?expired=1";
  const next = safeNext(pathname + search);
  const login = next ? `/login?expired=1&next=${encodeURIComponent(next)}` : "/login?expired=1";
  return `/_styx/exit?next=${encodeURIComponent(login)}`;
}

export const api = {
  listServices: () => request<ProxiedService[]>("/services"),
  /** Role-dependent shape: tiles for members, full services for admins. Always fetch fresh. */
  listServiceTiles: () => request<(ServiceTile | ProxiedService)[]>("/services"),
  listServicePresets: () => request<ServicePreset[]>("/services/presets"),
  discoverContainers: () => request<DiscoveredContainer[]>("/services/discover"),
  createService: (data: ProxiedServiceInput) =>
    request<ProxiedService>("/services", { method: "POST", body: JSON.stringify(data) }),
  updateService: (id: string, data: Omit<ProxiedServiceInput, "slug">) =>
    request<ProxiedService>(`/services/${id}`, { method: "PUT", body: JSON.stringify(data) }),
  deleteService: (id: string) => request<void>(`/services/${id}`, { method: "DELETE" }),
  setServiceIcon: (id: string, kind: "auto" | "emoji" | "image", value?: string) =>
    request<ProxiedService>(`/services/${id}/icon`, { method: "PUT", body: JSON.stringify({ kind, value }) }),
  refreshServiceIcon: (id: string) =>
    request<ProxiedService>(`/services/${id}/icon/refresh`, { method: "POST" }),
  setServiceEnabled: (id: string, enabled: boolean) =>
    request<ProxiedService>(`/services/${id}/${enabled ? "enable" : "disable"}`, { method: "POST" }),
  mountPlan: (id: string) => request<MountPlan>(`/services/${id}/mount/plan`, { method: "POST" }),
  /** `changes` are the ones the admin reviewed; the server refuses if the file moved since. */
  mountApply: (id: string, consent: boolean, changes?: MountChange[]) =>
    request<{ job_id: string }>(`/services/${id}/mount/apply`, { method: "POST", body: JSON.stringify({ consent, changes }) }),
  mountLatest: (id: string) => request<MountJob>(`/services/${id}/mount/jobs/latest`),
  serviceFocus: () => request<{ slug: string | null }>("/services/focus"),
  listGroups: () => request<Group[]>("/groups"),
  createGroup: (data: { name: string; description?: string | null }) =>
    request<Group>("/groups", { method: "POST", body: JSON.stringify(data) }),
  deleteGroup: (id: string) => request<void>(`/groups/${id}`, { method: "DELETE" }),
  updateGroup: (id: string, data: { allow_gpu?: boolean; description?: string | null }) =>
    request<Group>(`/groups/${id}`, { method: "PATCH", body: JSON.stringify(data) }),
  getMyProfiles: () => request<Profile[]>("/profiles"),
  deleteMyProfile: (templateId: string) => request<void>(`/profiles/${templateId}`, { method: "DELETE" }),
  getUserProfiles: (userId: string) => request<Profile[]>(`/users/${userId}/profiles`),
  deleteUserProfile: (userId: string, templateId: string) =>
    request<void>(`/users/${userId}/profiles/${templateId}`, { method: "DELETE" }),
  getUserGroups: (userId: string) => request<string[]>(`/users/${userId}/groups`),
  setUserGroups: (userId: string, groupIds: string[]) =>
    request<string[]>(`/users/${userId}/groups`, { method: "PUT", body: JSON.stringify({ group_ids: groupIds }) }),
  listInstances: () => request<Instance[]>("/instances"),
  screenshotUrl: (id: string) => `${BASE}/instances/${id}/screenshot`,
  workstationThumbUrl: (id: string) => `${BASE}/workstations/${id}/thumbnail`,
  serviceThumbUrl: (id: string) => `${BASE}/services/${id}/thumbnail`,
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
    removeImage = false,
    removeTemplate = false,
    deleteProfile = false,
  ) =>
    request<void>(
      `/instances/${id}?remove_image=${removeImage}&remove_template=${removeTemplate}&delete_profile=${deleteProfile}`,
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

  getRuntime: () => request<{ runtime: "docker" | "kubernetes" }>("/system/runtime"),
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
  setup: (data: { username: string; email?: string; password: string; setup_token: string }) =>
    request<{ id: string; username: string; role: string }>("/auth/setup", {
      method: "POST", body: JSON.stringify(data) }),
  login: (data: { username: string; password: string }) =>
    request<LoginResult>("/auth/login", {
      method: "POST", body: JSON.stringify(data) }),
  loginMatrix: (answers: string[]) =>
    request<LoginResult>("/auth/login/matrix", {
      method: "POST", body: JSON.stringify({ answers }) }),
  logout: (endSession = false) =>
    request<{ ok: boolean }>(
      `/auth/logout${endSession ? "?end_session=true" : ""}`,
      { method: "POST" },
    ),
  refreshSession: () => request<{ ok: boolean }>("/auth/refresh", { method: "POST" }),
  me: () => request<Me>("/auth/me"),
  setOpenPrefs: (p: Partial<Pick<Me, "open_workspaces" | "open_apps">>) =>
    request<Me>("/auth/me/preferences", { method: "PUT", body: JSON.stringify(p) }),
  acceptInvite: (data: { token: string; username: string; password: string }) =>
    request<{ id: string; username: string; role: string }>("/auth/accept-invite", {
      method: "POST", body: JSON.stringify(data) }),
  listUsers: () => request<{ id: string; username: string; email: string | null; role: string; is_active: boolean; last_login: string | null; locked_until: string | null; failed_count: number; has_matrix_card?: boolean }[]>("/users"),
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
  adminResetMatrix: (id: string) => request<{ ok: boolean }>(`/users/${id}/matrix`, { method: "DELETE" }),
  changePassword: (old_password: string, new_password: string) =>
    request("/auth/change-password", { method: "POST",
      body: JSON.stringify({ old_password, new_password }) }),

  matrixStatus: () => request<{ enabled: boolean }>("/auth/matrix"),
  matrixGenerate: (password: string) =>
    request<{ cells: Record<string, string>; confirm_cell: string }>("/auth/matrix/generate",
      { method: "POST", body: JSON.stringify({ password }) }),
  matrixActivate: (answer: string) =>
    request<{ enabled: boolean }>("/auth/matrix/activate",
      { method: "POST", body: JSON.stringify({ answer }) }),
  matrixRemove: (password: string) =>
    request("/auth/matrix", { method: "DELETE", body: JSON.stringify({ password }) }),

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
  setWorkstationIcon: (id: string, kind: "auto" | "emoji" | "image", value?: string) =>
    request<Workstation>(`/workstations/${id}/icon`, { method: "PUT", body: JSON.stringify({ kind, value }) }),
  revokeWorkstation: (id: string, purge = false) =>
    request<{ ok: boolean }>(`/workstations/${id}?purge=${purge}`, { method: "DELETE" }),
  workstationConnectUrl: (id: string, force = false) =>
    request<{ url: string }>(`/workstations/${id}/connect${force ? "?force=true" : ""}`),
  requestAgentUpdate: (id: string) =>
    request<Workstation>(`/workstations/${id}/agent-update`, { method: "POST" }),
  requestAgentUpdateOutdated: () =>
    request<{ requested: number }>("/workstations/agent-update-outdated", { method: "POST" }),
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
  getSystemSettings: () => request<SettingGroup[]>("/system-settings"),
  updateSystemSettings: (changes: Record<string, number | boolean | string>) =>
    request("/system-settings", { method: "PATCH", body: JSON.stringify(changes) }),
  resetSystemSetting: (key: string) =>
    request(`/system-settings/${key}/reset`, { method: "POST" }),
  getTurnUsage: (month?: string) =>
    request<TurnUsage>(`/admin/turn-usage${month ? `?month=${month}` : ""}`),
  getTurnCheck: () => request<TurnCheck>("/admin/turn-check"),
};
