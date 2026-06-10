import { useQuery } from "@tanstack/react-query";
import { motion, AnimatePresence } from "framer-motion";
import { api, type DiagCheck } from "@/api/client";
import { Button } from "@/components/ui/button";
import {
  RefreshCw,
  CheckCircle2,
  XCircle,
  AlertCircle,
} from "lucide-react";

const LABELS: Record<string, string> = {
  docker: "Docker engine",
  database: "Database",
  traefik_routes: "Traefik routing",
  disk: "Disk space",
  gpu: "GPU",
};

const HINTS: Record<string, string> = {
  traefik_routes:
    "Routes volume must be writable by the backend user — see the Production guide.",
  docker: "Is the docker-socket-proxy container healthy?",
  disk: "Free space is low — prune images or expand storage.",
};

function HealthCheck({ check }: { check: DiagCheck }) {
  const isOk = check.ok;
  const hint = HINTS[check.key];

  return (
    <motion.div
      initial={{ opacity: 0, y: 4 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -4 }}
      transition={{ duration: 0.2 }}
      className={`flex gap-3 rounded-lg border p-4 transition-all ${
        isOk
          ? "border-emerald-500/30 bg-emerald-500/5"
          : "border-rose-500/30 bg-rose-500/5"
      }`}
    >
      <div className="flex-shrink-0 pt-0.5">
        {isOk ? (
          <CheckCircle2 className="h-5 w-5 text-emerald-500" strokeWidth={2.5} />
        ) : (
          <XCircle className="h-5 w-5 text-rose-500" strokeWidth={2.5} />
        )}
      </div>

      <div className="flex-1 min-w-0">
        <div className="flex items-center justify-between gap-2 mb-1">
          <span className="text-sm font-semibold text-foreground">
            {LABELS[check.key] ?? check.key}
          </span>
          <span className="text-xs font-mono text-muted-foreground shrink-0">
            {check.latency_ms}ms
          </span>
        </div>
        <p className="text-xs text-muted-foreground leading-relaxed">
          {check.detail}
        </p>
        {!isOk && hint && (
          <p className="mt-2 text-xs text-amber-600 dark:text-amber-500 leading-relaxed">
            {hint}
          </p>
        )}
      </div>
    </motion.div>
  );
}

function HistoryStrip({ series }: { series: boolean[] }) {
  return (
    <div className="flex gap-0.5">
      {series.map((up, i) => (
        <motion.div
          key={i}
          initial={{ opacity: 0.5 }}
          animate={{ opacity: 1 }}
          className={`h-6 flex-1 rounded-sm transition-colors ${
            up
              ? "bg-emerald-500/70"
              : "bg-rose-500/70"
          }`}
          title={up ? "Healthy" : "Failed"}
        />
      ))}
    </div>
  );
}

export function HealthPanel() {
  const { data, isLoading, refetch, isFetching } = useQuery({
    queryKey: ["diagnostics"],
    queryFn: api.getDiagnostics,
    refetchInterval: 30000,
  });

  const { data: history } = useQuery({
    queryKey: ["diagnostics-history"],
    queryFn: () => api.getDiagnosticsHistory("1h"),
    refetchInterval: 60000,
  });

  const allHealthy = data?.ok ?? false;
  const checks = data?.checks ?? [];

  return (
    <div className="space-y-6">
      {/* Header with refresh */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold text-foreground">System health</h2>
          <p className="text-sm text-muted-foreground mt-1">
            Real-time diagnostic checks and 1-hour history
          </p>
        </div>
        <Button
          size="sm"
          variant="outline"
          disabled={isFetching}
          onClick={() => refetch()}
          className="gap-2"
        >
          <RefreshCw
            className={`h-4 w-4 ${isFetching ? "animate-spin" : ""}`}
            strokeWidth={2}
          />
          Run checks
        </Button>
      </div>

      {/* Status banner */}
      <AnimatePresence mode="wait">
        {data && (
          <motion.div
            key={`status-${allHealthy}`}
            initial={{ opacity: 0, y: -4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -4 }}
            transition={{ duration: 0.2 }}
            className={`flex items-center gap-3 rounded-lg border px-4 py-3 text-sm font-medium ${
              allHealthy
                ? "border-emerald-500/30 bg-emerald-500/5 text-emerald-700 dark:text-emerald-400"
                : "border-rose-500/30 bg-rose-500/5 text-rose-700 dark:text-rose-400"
            }`}
          >
            {allHealthy ? (
              <CheckCircle2 className="h-5 w-5 shrink-0" strokeWidth={2.5} />
            ) : (
              <AlertCircle className="h-5 w-5 shrink-0" strokeWidth={2.5} />
            )}
            <span>
              {allHealthy
                ? "All systems operational"
                : `${checks.filter((c) => !c.ok).length} of ${checks.length} check${checks.length !== 1 ? "s" : ""} failing`}
            </span>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Checks list */}
      <div className="space-y-2">
        {isLoading ? (
          <div className="flex items-center justify-center py-8">
            <div className="space-y-3 w-full">
              {[...Array(3)].map((_, i) => (
                <div
                  key={i}
                  className="h-20 rounded-lg bg-muted/40 animate-pulse"
                />
              ))}
            </div>
          </div>
        ) : checks.length > 0 ? (
          <AnimatePresence mode="popLayout">
            {checks.map((check) => (
              <HealthCheck key={check.key} check={check} />
            ))}
          </AnimatePresence>
        ) : (
          <div className="py-8 text-center text-sm text-muted-foreground">
            No diagnostic data available
          </div>
        )}
      </div>

      {/* History strip */}
      {history &&
        Object.keys(history.status).length > 0 && (
          <div className="space-y-3 border-t pt-6">
            <h3 className="text-sm font-semibold text-foreground">
              Health trend (last 60 minutes)
            </h3>
            <div className="space-y-2">
              {Object.entries(history.status).map(([key, series]) => (
                <motion.div
                  key={key}
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  transition={{ delay: 0.05 }}
                  className="flex items-center gap-3"
                >
                  <span className="w-24 shrink-0 text-xs font-medium text-muted-foreground">
                    {LABELS[key] ?? key}
                  </span>
                  <div className="flex-1">
                    <HistoryStrip series={series as boolean[]} />
                  </div>
                </motion.div>
              ))}
            </div>
            <p className="text-xs text-muted-foreground">
              Each column represents a 1-minute interval
            </p>
          </div>
        )}
    </div>
  );
}
