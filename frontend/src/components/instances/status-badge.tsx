import { cn } from "@/lib/utils";

const STATUS_STYLES: Record<string, { dot: string; text: string }> = {
  running: { dot: "bg-success", text: "text-success" },
  idle: { dot: "bg-warning", text: "text-warning" },
  stopped: { dot: "bg-muted-foreground", text: "text-muted-foreground" },
  error: { dot: "bg-destructive", text: "text-destructive" },
  creating: { dot: "bg-primary", text: "text-primary" },
  starting: { dot: "bg-primary", text: "text-primary" },
  stopping: { dot: "bg-warning", text: "text-warning" },
};

export function StatusBadge({ status }: { status: string }) {
  const style = STATUS_STYLES[status] ?? STATUS_STYLES.stopped;
  return (
    <span className={cn("flex items-center gap-1.5 text-xs font-medium", style.text)}>
      <span className={cn("h-1.5 w-1.5 rounded-full", style.dot)} />
      {status.charAt(0).toUpperCase() + status.slice(1)}
    </span>
  );
}
