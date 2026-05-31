import { useState, useEffect, useRef, useCallback } from "react";
import { motion } from "framer-motion";
import { cn } from "@/lib/utils";
import { useInstances } from "@/hooks/use-instances";
import { useLogs } from "@/hooks/use-system";
import {
  Search,
  Terminal,
  Radio,
  ArrowDown,
} from "lucide-react";

export function MetricsLogs() {
  const { data: instances } = useInstances();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [liveTail, setLiveTail] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [autoScroll, setAutoScroll] = useState(true);
  const logContainerRef = useRef<HTMLDivElement>(null);

  const { data: logs, refetch } = useLogs(selectedId, liveTail);

  // Auto-select first running instance
  useEffect(() => {
    if (!selectedId && instances?.length) {
      const running = instances.find((i) => i.status === "running" || i.status === "idle");
      if (running) setSelectedId(running.id);
      else setSelectedId(instances[0]!.id);
    }
  }, [instances, selectedId]);

  // Auto-scroll to bottom
  useEffect(() => {
    if (autoScroll && logContainerRef.current) {
      logContainerRef.current.scrollTop = logContainerRef.current.scrollHeight;
    }
  }, [logs, autoScroll]);

  const handleScroll = useCallback(() => {
    if (!logContainerRef.current) return;
    const { scrollTop, scrollHeight, clientHeight } = logContainerRef.current;
    setAutoScroll(scrollHeight - scrollTop - clientHeight < 50);
  }, []);

  const filteredLogs = searchQuery
    ? logs?.filter((line) => line.toLowerCase().includes(searchQuery.toLowerCase()))
    : logs;

  const selectedInstance = instances?.find((i) => i.id === selectedId);

  return (
    <div className="space-y-3">
      {/* Controls bar */}
      <div className="flex items-center gap-3 flex-wrap">
        {/* Instance selector */}
        <select
          value={selectedId ?? ""}
          onChange={(e) => { setSelectedId(e.target.value); setLiveTail(false); }}
          className="rounded-md border border-border bg-background px-3 py-1.5 text-xs text-foreground outline-none focus:border-border min-w-[180px]"
        >
          <option value="" disabled>Select instance…</option>
          {instances?.map((inst) => (
            <option key={inst.id} value={inst.id}>
              {inst.name} ({inst.status})
            </option>
          ))}
        </select>

        {/* Live tail toggle */}
        <button
          onClick={() => setLiveTail(!liveTail)}
          disabled={!selectedId}
          className={cn(
            "flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-[11px] font-medium transition-colors border",
            liveTail
              ? "border-emerald-500/40 bg-emerald-500/10 text-emerald-400"
              : "border-border text-muted-foreground hover:text-foreground/80 hover:border-border"
          )}
        >
          {liveTail ? <Radio className="h-3 w-3 animate-pulse" /> : <Terminal className="h-3 w-3" />}
          {liveTail ? "Streaming" : "Live Tail"}
        </button>

        {/* Search */}
        <div className="relative flex-1 min-w-[150px] max-w-[300px]">
          <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3 w-3 text-muted-foreground/60" />
          <input
            type="text"
            placeholder="Filter logs…"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full rounded-md border border-border bg-background pl-7 pr-3 py-1.5 text-xs text-foreground placeholder:text-muted-foreground/60 outline-none focus:border-border"
          />
        </div>

        {/* Actions */}
        <div className="flex gap-1 ml-auto">
          <button
            onClick={() => refetch()}
            disabled={!selectedId}
            title="Refresh"
            className="rounded p-1.5 text-muted-foreground hover:text-foreground/80 hover:bg-muted/50 transition-colors"
          >
            <ArrowDown className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>

      {/* Log viewer */}
      <div className="rounded-lg border border-border bg-background overflow-hidden">
        {/* Log header */}
        <div className="flex items-center justify-between px-3 py-2 border-b border-border/40 bg-card">
          <div className="flex items-center gap-2">
            <Terminal className="h-3 w-3 text-muted-foreground/60" />
            <span className="text-[11px] text-muted-foreground font-mono">
              {selectedInstance ? `${selectedInstance.name}` : "No instance selected"}
            </span>
          </div>
          <div className="flex items-center gap-2">
            {liveTail && (
              <span className="flex items-center gap-1 text-[10px] text-emerald-500">
                <span className="h-1.5 w-1.5 rounded-full bg-emerald-500 animate-pulse" />
                LIVE
              </span>
            )}
            <span className="text-[10px] text-muted-foreground/60 tabular-nums">
              {filteredLogs?.length ?? 0} lines
            </span>
          </div>
        </div>

        {/* Log content */}
        <div
          ref={logContainerRef}
          onScroll={handleScroll}
          className="h-[400px] overflow-y-auto overflow-x-auto p-3 font-mono text-[11px] leading-[1.6] select-text"
        >
          {!selectedId ? (
            <div className="flex items-center justify-center h-full text-muted-foreground/60 text-xs">
              Select an instance to view logs
            </div>
          ) : !filteredLogs || filteredLogs.length === 0 ? (
            <div className="flex items-center justify-center h-full text-muted-foreground/60 text-xs">
              {searchQuery ? "No matching lines" : "No logs available"}
            </div>
          ) : (
            filteredLogs.map((line, i) => (
              <LogLine key={i} line={line} lineNum={i + 1} query={searchQuery} />
            ))
          )}
        </div>

        {/* Scroll-to-bottom indicator */}
        {!autoScroll && (
          <motion.button
            initial={{ opacity: 0, y: 5 }}
            animate={{ opacity: 1, y: 0 }}
            onClick={() => {
              if (logContainerRef.current) {
                logContainerRef.current.scrollTop = logContainerRef.current.scrollHeight;
                setAutoScroll(true);
              }
            }}
            className="absolute bottom-4 right-4 rounded-full bg-secondary border border-border p-2 text-muted-foreground hover:text-foreground shadow-lg"
          >
            <ArrowDown className="h-3.5 w-3.5" />
          </motion.button>
        )}
      </div>
    </div>
  );
}

function LogLine({ line, lineNum, query }: { line: string; lineNum: number; query: string }) {
  const isError = /error|fatal|panic|exception/i.test(line);
  const isWarn = /warn|warning/i.test(line);

  let highlighted = line;
  if (query) {
    const regex = new RegExp(`(${query.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")})`, "gi");
    highlighted = line.replace(regex, "<<<MARK>>>$1<<<ENDMARK>>>");
  }

  return (
    <div className={cn(
      "flex gap-2 py-px hover:bg-muted/30 rounded-sm transition-colors",
      isError && "bg-destructive/10",
      isWarn && "bg-warning/10"
    )}>
      <span className="text-muted-foreground/40 select-none w-8 text-right shrink-0 tabular-nums">
        {lineNum}
      </span>
      <span className={cn(
        "whitespace-pre",
        isError ? "text-destructive" : isWarn ? "text-warning" : "text-muted-foreground"
      )}>
        {query ? (
          highlighted.split("<<<MARK>>>").map((part, i) => {
            if (i === 0) return part;
            const [match, ...rest] = part.split("<<<ENDMARK>>>");
            return (
              <span key={i}>
                <mark className="bg-warning/30 text-warning rounded-sm px-0.5">{match}</mark>
                {rest.join("")}
              </span>
            );
          })
        ) : line}
      </span>
    </div>
  );
}
