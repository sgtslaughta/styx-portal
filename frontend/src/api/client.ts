import type {
  Instance,
  InstanceCreate,
  InstanceStatus,
  PulledImage,
  RegistryImage,
  ServiceTemplate,
  TemplateCreate,
} from "@/lib/types";

const BASE = "/api";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...init?.headers },
    ...init,
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(detail.detail || res.statusText);
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}

export const api = {
  listInstances: () => request<Instance[]>("/instances"),
  createInstance: (data: InstanceCreate) =>
    request<Instance>("/instances", { method: "POST", body: JSON.stringify(data) }),
  startInstance: (id: string) =>
    request<Instance>(`/instances/${id}/start`, { method: "POST" }),
  stopInstance: (id: string) =>
    request<Instance>(`/instances/${id}/stop`, { method: "POST" }),
  restartInstance: (id: string) =>
    request<Instance>(`/instances/${id}/restart`, { method: "POST" }),
  pauseInstance: (id: string) =>
    request<Instance>(`/instances/${id}/pause`, { method: "POST" }),
  unpauseInstance: (id: string) =>
    request<Instance>(`/instances/${id}/unpause`, { method: "POST" }),
  updateInstance: (id: string, data: { name?: string; env_overrides?: Record<string, string>; session_config?: Record<string, unknown> }) =>
    request<Instance>(`/instances/${id}`, { method: "PATCH", body: JSON.stringify(data) }),
  deleteInstance: (id: string, removeVolumes = false) =>
    request<void>(`/instances/${id}?remove_volumes=${removeVolumes}`, { method: "DELETE" }),
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
};
