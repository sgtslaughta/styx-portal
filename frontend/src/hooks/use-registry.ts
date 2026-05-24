import { useQuery } from "@tanstack/react-query";
import { useState, useEffect } from "react";
import { api } from "@/api/client";

function useDebounce<T>(value: T, delay: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(timer);
  }, [value, delay]);
  return debounced;
}

export function useRegistryImages(params?: { category?: string; search?: string }) {
  const debouncedSearch = useDebounce(params?.search, 300);
  return useQuery({
    queryKey: ["registry", params?.category, debouncedSearch],
    queryFn: () => api.listRegistryImages({ category: params?.category, search: debouncedSearch }),
    staleTime: 60 * 60 * 1000,
    enabled: debouncedSearch === undefined || debouncedSearch.length !== 1,
  });
}

export function useRegistryImage(name: string) {
  return useQuery({
    queryKey: ["registry", name],
    queryFn: () => api.getRegistryImage(name),
    enabled: !!name,
  });
}
