import { useQuery } from "@tanstack/react-query";
import { api } from "@/api/client";

export function useIsK8s() {
  const { data } = useQuery({
    queryKey: ["runtime"],
    queryFn: api.getRuntime,
    staleTime: Infinity,
  });
  return data?.runtime === "kubernetes";
}

export function useGpuInfo() {
  return useQuery({
    queryKey: ["gpu-info"],
    queryFn: api.getGpuInfo,
    staleTime: 60000,
  });
}
