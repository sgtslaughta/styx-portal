import { useQuery } from "@tanstack/react-query";
import { api } from "@/api/client";
import { useAdminPoll } from "@/hooks/use-admin-poll";

export function useSystemMetrics() {
  return useQuery({
    queryKey: ["system-metrics"],
    queryFn: api.getSystemMetrics,
    refetchInterval: 10000,
  });
}

export function useSessionEvents(instanceId: string, enabled: boolean) {
  return useQuery({
    queryKey: ["session-events", instanceId],
    queryFn: () => api.getSessionEvents(instanceId),
    enabled,
  });
}

export function useResourceHistory(range: string) {
  const poll = useAdminPoll(30000);
  return useQuery({
    queryKey: ["resource-history", range],
    queryFn: () => api.getResourceHistory(range),
    refetchInterval: poll,
  });
}

export function useLogs(instanceId: string | null, live: boolean) {
  return useQuery({
    queryKey: ["instance-logs", instanceId, live],
    queryFn: () => api.getInstanceLogs(instanceId!),
    enabled: !!instanceId,
    refetchInterval: live ? 3000 : false,
  });
}
