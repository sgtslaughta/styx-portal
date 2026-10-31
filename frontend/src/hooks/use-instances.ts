import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/api/client";
import { toast } from "sonner";
import type { Instance, InstanceCreate } from "@/lib/types";

const BUSY = ["starting", "pulling"];
const prevStatus = new Map<string, string>();

/** Toast once when an instance we saw starting/pulling becomes running. */
function notifyReady(list: Instance[]) {
  for (const i of list) {
    const was = prevStatus.get(i.id);
    if (was && BUSY.includes(was) && i.status === "running") {
      toast.success(`${i.name} is ready`, {
        id: `ready-${i.id}`,
        action: { label: "Open", onClick: () => window.open(`/desktop/${i.subdomain}`, "_blank") },
      });
    }
    prevStatus.set(i.id, i.status);
  }
}

export function useInstances() {
  return useQuery({
    queryKey: ["instances"],
    queryFn: async () => {
      const list = await api.listInstances();
      notifyReady(list);
      return list;
    },
    refetchInterval: (q) => (q.state.data?.some((i) => BUSY.includes(i.status)) ? 2000 : 5000),
  });
}

export function useCreateInstance() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: InstanceCreate) => api.createInstance(data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["instances"] }),
  });
}

export function useStartInstance() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.startInstance(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["instances"] }),
  });
}

export function useStopInstance() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.stopInstance(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["instances"] }),
  });
}

export function useRestartInstance() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.restartInstance(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["instances"] }),
  });
}

export function useRecreateInstance() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.recreateInstance(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["instances"] }),
  });
}

export function usePauseInstance() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.pauseInstance(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["instances"] }),
  });
}

export function useUnpauseInstance() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.unpauseInstance(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["instances"] }),
  });
}

export function useUpdateInstance() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: { name?: string; env_overrides?: Record<string, string>; session_config?: Record<string, unknown> } }) =>
      api.updateInstance(id, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["instances"] }),
  });
}

export function useDeleteInstance() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, removeImage, removeTemplate, deleteProfile }: {
      id: string;
      removeImage?: boolean;
      removeTemplate?: boolean;
      deleteProfile?: boolean;
    }) => api.deleteInstance(id, removeImage ?? false, removeTemplate ?? false, deleteProfile ?? false),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["instances"] }),
  });
}

export function useInstanceStats(id: string, enabled: boolean) {
  return useQuery({
    queryKey: ["instance-stats", id],
    queryFn: () => api.getInstanceStats(id),
    refetchInterval: 5000,
    enabled,
  });
}

export function useInstanceStatus(id: string, enabled: boolean) {
  return useQuery({
    queryKey: ["instance-status", id],
    queryFn: () => api.getInstanceStatus(id),
    refetchInterval: 2000,
    enabled,
  });
}

export function useKeepalive() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.keepalive(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["instances"] }),
  });
}
