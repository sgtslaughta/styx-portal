import { useQuery } from "@tanstack/react-query";
import { api, ApiError } from "@/api/client";

export function useOverviewStats(range: string) {
  return useQuery({ queryKey: ["stats-overview", range], queryFn: () => api.getOverviewStats(range), refetchInterval: 60000 });
}
export function useStreamingStats() {
  return useQuery({ queryKey: ["stats-streaming"], queryFn: () => api.getStreamingStats(7, 5), refetchInterval: 120000 });
}
export function useRelayStats(period: string, enabled = true) {
  return useQuery({
    queryKey: ["stats-relay", period], queryFn: () => api.getRelayStats(period), enabled,
    retry: (n, e) => !(e instanceof ApiError && e.status === 404) && n < 2,
  });
}

/** Cheap "Cloudflare analytics configured" signal: both settings are set (secrets report is_set). */
export function useCfAnalytics(enabled = true): boolean {
  const { data } = useQuery({ queryKey: ["system-settings"], queryFn: api.getSystemSettings, enabled });
  const all = (data ?? []).flatMap((g) => g.settings);
  const set = (k: string) => {
    const s = all.find((x) => x.key === k);
    return !!s && (s.is_set === true || (typeof s.value === "string" && s.value !== ""));
  };
  return set("CLOUDFLARE_ACCOUNT_ID") && set("CLOUDFLARE_ANALYTICS_TOKEN");
}
