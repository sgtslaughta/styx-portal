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

export function useDeleteInstance() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, removeVolumes }: { id: string; removeVolumes: boolean }) =>
      api.deleteInstance(id, removeVolumes),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["instances"] }),
  });
}
