import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/api/client";
import type { InstanceCreate } from "@/lib/types";

export function useInstances() {
  return useQuery({
    queryKey: ["instances"],
    queryFn: api.listInstances,
    refetchInterval: 5000,
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
    mutationFn: ({ id, removeVolumes }: { id: string; removeVolumes: boolean }) =>
      api.deleteInstance(id, removeVolumes),
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
