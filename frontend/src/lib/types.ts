export interface SessionConfig {
  idle_timeout: string;
  grace_period: string;
  timeout_action: "stop" | "destroy";
  never_timeout: boolean;
  max_session_duration: string | null;
}

export interface ServiceTemplate {
  id: string;
  name: string;
  display_name: string;
  image: string;
  icon: string | null;
  description: string | null;
  env_vars: Record<string, string>;
  gpu_enabled: boolean;
  gpu_count: number;
  memory_limit: string | null;
  cpu_limit: string | null;
  shm_size: string | null;
  volumes: { name: string; mount: string }[];
  internal_port: number;
  internal_protocol: string;
  category: string | null;
  tags: string[];
  session_config: SessionConfig;
  created_at: string;
  updated_at: string;
}

export interface Instance {
  id: string;
  template_id: string;
  name: string;
  subdomain: string;
  container_id: string | null;
  status: "created" | "creating" | "pulling" | "starting" | "running" | "idle" | "paused" | "stopping" | "stopped" | "error";
  env_overrides: Record<string, string>;
  volume_names: string[];
  created_at: string;
  started_at: string | null;
  stopped_at: string | null;
  last_activity: string | null;
  session_config: SessionConfig | null;
}

export interface InstanceStatus {
  id: string;
  status: string;
  container_id: string | null;
  uptime_seconds: number | null;
  idle_seconds: number | null;
  session_config: SessionConfig | null;
}

export interface RegistryImage {
  name: string;
  description: string;
  project_logo: string;
  category: string;
  stars: number;
  monthly_pulls: number;
  version: string;
  stable: boolean;
  tags: { tag: string; desc: string }[];
  config: {
    application_setup?: string;
    env_vars: { name: string; value: string; desc: string; optional: boolean }[];
    volumes: { path: string; host_path: string; desc: string; optional: boolean }[];
    ports: { external: string; internal: string; desc: string; optional: boolean }[];
    custom?: { name: string; name_compose: string; value: string; desc: string; optional: boolean }[];
    security_opt?: { run_var: string; compose_var: string; desc: string; optional: boolean }[];
  };
  architectures: { arch: string; tag: string }[];
  changelog?: { date: string; desc: string }[];
  github_url: string;
  project_url: string;
}

export interface InstanceCreate {
  template_id: string;
  name: string;
  subdomain: string;
  env_overrides?: Record<string, string>;
  session_config?: Partial<SessionConfig>;
}

export interface TemplateCreate {
  name: string;
  display_name: string;
  image: string;
  icon?: string;
  description?: string;
  env_vars?: Record<string, string>;
  gpu_enabled?: boolean;
  gpu_count?: number;
  memory_limit?: string;
  cpu_limit?: string;
  shm_size?: string;
  volumes?: { name: string; mount: string }[];
  internal_port?: number;
  internal_protocol?: string;
  category?: string;
  tags?: string[];
  session_config?: Partial<SessionConfig>;
}

export interface PulledImage {
  id: string;
  image: string;
  size_mb: number | null;
  pulled_at: string;
}
