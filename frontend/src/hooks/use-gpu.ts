import { useQuery } from "@tanstack/react-query";
import { api } from "@/api/client";

export function useGpuInfo() {
  return useQuery({
    queryKey: ["gpu-info"],
    queryFn: api.getGpuInfo,
    staleTime: 60000,
  });
}
