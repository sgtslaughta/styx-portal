import { useQuery } from "@tanstack/react-query";
import { api } from "@/api/client";

export function useRegistryImages(params?: { category?: string; search?: string }) {
  return useQuery({
    queryKey: ["registry", params?.category, params?.search],
    queryFn: () => api.listRegistryImages(params),
    staleTime: 60 * 60 * 1000,
  });
}

export function useRegistryImage(name: string) {
  return useQuery({
    queryKey: ["registry", name],
    queryFn: () => api.getRegistryImage(name),
    enabled: !!name,
  });
}
