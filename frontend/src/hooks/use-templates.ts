import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/api/client";
import type { TemplateCreate } from "@/lib/types";

export function useTemplates(opts?: { shared?: boolean }) {
  const shared = !!opts?.shared;
  return useQuery({
    queryKey: shared ? ["templates", "shared"] : ["templates"],
    queryFn: () => api.listTemplates(shared),
  });
}

export function useSizePresets() {
  return useQuery({ queryKey: ["size-presets"], queryFn: api.getSizePresets, staleTime: 5 * 60 * 1000 });
}

export function useCreateTemplate() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: TemplateCreate) => api.createTemplate(data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["templates"] }),
  });
}

export function useUpdateTemplate() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: Partial<TemplateCreate> }) => api.updateTemplate(id, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["templates"] }),
  });
}

export function useDeleteTemplate() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.deleteTemplate(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["templates"] }),
  });
}
