import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/api/client";

export function useImages() {
  return useQuery({
    queryKey: ["images"],
    queryFn: api.listImages,
  });
}

export function useDeleteImage() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.deleteImage(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["images"] }),
  });
}

export function usePurgeImages() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api.purgeImages(),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["images"] }),
  });
}
