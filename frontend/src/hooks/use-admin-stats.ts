import { useQuery } from "@tanstack/react-query";
import { api, ApiError } from "@/api/client";
import { useAdminPoll } from "@/hooks/use-admin-poll";

export function useOverviewStats(range: string) {
  const poll = useAdminPoll(60000);
  return useQuery({ queryKey: ["stats-overview", range], queryFn: () => api.getOverviewStats(range), refetchInterval: poll });
}
export function useStreamingStats() {
  const poll = useAdminPoll(120000);
  return useQuery({ queryKey: ["stats-streaming"], queryFn: () => api.getStreamingStats(7, 5), refetchInterval: poll });
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
