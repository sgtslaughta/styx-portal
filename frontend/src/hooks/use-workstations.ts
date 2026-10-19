import { useQuery } from "@tanstack/react-query";
import { api } from "@/api/client";

/** Workstations this user may open (polled; the list and the pane share it). */
export function useMyWorkstations() {
  return useQuery({ queryKey: ["my-workstations"], queryFn: api.myWorkstations, refetchInterval: 15_000 });
}
