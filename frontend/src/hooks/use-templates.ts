import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/api/client";
import type { TemplateCreate } from "@/lib/types";

export function useTemplates() {
  return useQuery({
    queryKey: ["templates"],
    queryFn: api.listTemplates,
  });
}

export function useCreateTemplate() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: TemplateCreate) => api.createTemplate(data),
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
