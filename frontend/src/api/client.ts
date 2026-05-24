import type {
  Instance,
  InstanceCreate,
  InstanceStatus,
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
  deleteInstance: (id: string, removeVolumes = false) =>
    request<void>(`/instances/${id}?remove_volumes=${removeVolumes}`, { method: "DELETE" }),
  getInstanceStatus: (id: string) =>
    request<InstanceStatus>(`/instances/${id}/status`),
  keepalive: (id: string) =>
    request<Instance>(`/instances/${id}/keepalive`, { method: "POST" }),
  screenshotUrl: (id: string) => `${BASE}/instances/${id}/screenshot`,

  listTemplates: () => request<ServiceTemplate[]>("/templates"),
  createTemplate: (data: TemplateCreate) =>
    request<ServiceTemplate>("/templates", { method: "POST", body: JSON.stringify(data) }),
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
};
