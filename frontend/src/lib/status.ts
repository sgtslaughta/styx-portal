import {
  Activity, AlertTriangle, Clock, Download, Loader2, Pause, Power, Square,
  type LucideIcon,
} from "lucide-react";

export type InstanceStatusValue =
  | "created" | "creating" | "pulling" | "starting" | "running"
  | "idle" | "paused" | "stopping" | "stopped" | "error";

export type StatusGroup =
  | "running" | "paused" | "transition" | "stopped" | "error";

export interface StatusMeta {
  label: string;
  /** Tailwind text color class, e.g. "text-success". */
  textClass: string;
  /** Tailwind background class for the status dot, e.g. "bg-success". */
  dotClass: string;
  icon: LucideIcon;
  /** Whether the dot/icon should pulse. */
  pulse: boolean;
  group: StatusGroup;
}

export const STATUS_META: Record<InstanceStatusValue, StatusMeta> = {
  created:  { label: "Created",  textClass: "text-muted-foreground", dotClass: "bg-muted-foreground", icon: Power,         pulse: false, group: "stopped" },
  creating: { label: "Creating", textClass: "text-primary",          dotClass: "bg-primary",          icon: Loader2,       pulse: true,  group: "transition" },
  pulling:  { label: "Pulling",  textClass: "text-primary",          dotClass: "bg-primary",          icon: Download,      pulse: true,  group: "transition" },
  starting: { label: "Starting", textClass: "text-primary",          dotClass: "bg-primary",          icon: Loader2,       pulse: true,  group: "transition" },
  running:  { label: "Running",  textClass: "text-success",          dotClass: "bg-success",          icon: Activity,      pulse: true,  group: "running" },
  idle:     { label: "Idle",     textClass: "text-warning",          dotClass: "bg-warning",          icon: Clock,         pulse: false, group: "running" },
  paused:   { label: "Paused",   textClass: "text-warning",          dotClass: "bg-warning",          icon: Pause,         pulse: false, group: "paused" },
  stopping: { label: "Stopping", textClass: "text-warning",          dotClass: "bg-warning",          icon: Loader2,       pulse: true,  group: "transition" },
  stopped:  { label: "Stopped",  textClass: "text-muted-foreground", dotClass: "bg-muted-foreground", icon: Square,        pulse: false, group: "stopped" },
  error:    { label: "Error",    textClass: "text-destructive",      dotClass: "bg-destructive",      icon: AlertTriangle, pulse: false, group: "error" },
};

export function statusMeta(status: string): StatusMeta {
  return STATUS_META[status as InstanceStatusValue] ?? STATUS_META.stopped;
}

export const RUNNING_STATUSES = new Set<string>(["running", "idle"]);
export const TRANSITION_STATUSES = new Set<string>(["creating", "pulling", "starting", "stopping"]);

export function isRunning(status: string): boolean { return RUNNING_STATUSES.has(status); }
export function isTransitioning(status: string): boolean { return TRANSITION_STATUSES.has(status); }
