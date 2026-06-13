import { useState } from "react";
import { slugify } from "@/lib/utils";
import type {
  RegistryImage,
  ServiceTemplate,
  Instance,
  ExtraPortEntry,
} from "@/lib/types";

export type { ExtraPortEntry };

export interface VolumeEntry {
  name: string;
  mount: string;
  desc?: string;
}

export interface PortEntry {
  internal: string;
  external: string;
  desc?: string;
}

export interface SecurityOpt {
  value: string;
  desc?: string;
  enabled: boolean;
}

export interface CustomOpt {
  name: string;
  value: string;
  desc?: string;
}

export interface LaunchConfig {
  name: string;
  setName: (v: string) => void;
  subdomain: string;
  setSubdomain: (v: string) => void;
  image: string;
  setImage: (v: string) => void;
  icon: string;
  setIcon: (v: string) => void;
  memoryLimit: string;
  setMemoryLimit: (v: string) => void;
  cpuLimit: string;
  setCpuLimit: (v: string) => void;
  shmSize: string;
  setShmSize: (v: string) => void;
  envVars: Record<string, string>;
  setEnvVars: (v: Record<string, string>) => void;
  envDescriptions: Record<string, string>;
  gpuEnabled: boolean;
  setGpuEnabled: (v: boolean) => void;
  gpuDevices: string[];
  setGpuDevices: (v: string[]) => void;
  volumes: VolumeEntry[];
  setVolumes: (v: VolumeEntry[]) => void;
  ports: PortEntry[];
  setPorts: (v: PortEntry[]) => void;
  securityOpts: SecurityOpt[];
  setSecurityOpts: (v: SecurityOpt[]) => void;
  customOpts: CustomOpt[];
  setCustomOpts: (v: CustomOpt[]) => void;
  idleTimeout: string;
  setIdleTimeout: (v: string) => void;
  gracePeriod: string;
  setGracePeriod: (v: string) => void;
  internalPort: number;
  setInternalPort: (v: number) => void;
  internalProtocol: string;
  setInternalProtocol: (v: string) => void;
  restartPolicy: string;
  setRestartPolicy: (v: string) => void;
  readOnlyRootfs: boolean;
  setReadOnlyRootfs: (v: boolean) => void;
  tmpfs: string[];
  setTmpfs: (v: string[]) => void;
  extraHosts: Record<string, string>;
  setExtraHosts: (v: Record<string, string>) => void;
  ulimits: { name: string; soft: number; hard: number }[];
  setUlimits: (v: { name: string; soft: number; hard: number }[]) => void;
  extraPorts: ExtraPortEntry[];
  setExtraPorts: (v: ExtraPortEntry[]) => void;
  entrypoint: string[] | null;
  setEntrypoint: (v: string[] | null) => void;
  command: string[] | null;
  setCommand: (v: string[] | null) => void;
  devices: string[];
  setDevices: (v: string[]) => void;
  privileged: boolean;
  setPrivileged: (v: boolean) => void;
  extraDockerArgs: Record<string, unknown>;
  setExtraDockerArgs: (v: Record<string, unknown>) => void;
  shared: boolean;
  setShared: (v: boolean) => void;
  buildTemplateData: () => {
    name: string;
    display_name: string;
    image: string;
    icon: string | undefined;
    description: string;
    env_vars: Record<string, string>;
    gpu_enabled: boolean;
    gpu_count: number;
    memory_limit: string;
    cpu_limit: string;
    shm_size: string;
    volumes: { name: string; mount: string }[];
    internal_port: number;
    internal_protocol: string;
    category: string | undefined;
    tags: string[];
    session_config: { idle_timeout: string; grace_period: string; timeout_action: "stop"; never_timeout: boolean; max_session_duration: null };
    security_opts: string[] | undefined;
    custom_opts: Record<string, string> | undefined;
    restart_policy: string;
    read_only_rootfs: boolean;
    tmpfs: string[];
    extra_hosts: Record<string, string>;
    ulimits: { name: string; soft: number; hard: number }[];
    extra_ports: ExtraPortEntry[];
    entrypoint: string[] | null;
    command: string[] | null;
    devices: string[];
    privileged: boolean;
    extra_docker_args: Record<string, unknown>;
    shared: boolean;
  };
}

/**
 * Determine the web UI port + protocol for an instance.
 *  1. An existing template's stored value wins (covers user overrides + edits).
 *  2. Otherwise derive from the registry image's declared ports — LinuxServer.io
 *     lists each port with a desc (e.g. "...HTTPS." / "...HTTP, must be proxied").
 *     Prefer the HTTPS port, then HTTP, then the first declared port.
 *  3. Fallback to 3001/https (the Selkies default + backend default).
 * The result is only a PREFILL — the user can override it in the UI.
 */
function detectPortAndProtocol(
  registryImage: RegistryImage | null | undefined,
  template: ServiceTemplate | null | undefined
): { port: number; protocol: string } {
  if (template?.internal_port) {
    return { port: template.internal_port, protocol: template.internal_protocol || "https" };
  }
  const ports = registryImage?.config?.ports ?? [];
  const https = ports.find((p) => /https/i.test(p.desc ?? ""));
  if (https) return { port: Number(https.internal), protocol: "https" };
  const http = ports.find((p) => /http/i.test(p.desc ?? ""));
  if (http) return { port: Number(http.internal), protocol: "http" };
  if (ports[0]?.internal) return { port: Number(ports[0].internal), protocol: "https" };
  return { port: 3001, protocol: "https" };
}

export function useLaunchConfig(opts: {
  registryImage?: RegistryImage | null;
  template?: ServiceTemplate | null;
  instance?: Instance | null;
}): LaunchConfig {
  const { registryImage, template, instance } = opts;

  // Prefill logic
  const prefillName = instance
    ? instance.name
    : registryImage?.name ?? template?.display_name ?? "";
  const registryTag = registryImage?.tags?.[0]?.tag ?? "latest";
  const prefillImage = registryImage
    ? `lscr.io/linuxserver/${registryImage.name}:${registryTag}`
    : template?.image ?? "";

  // Env vars with descriptions
  const prefillEnv: Record<string, string> = {};
  const envDescriptions: Record<string, string> = {};
  if (registryImage?.config?.env_vars) {
    for (const v of registryImage.config.env_vars) {
      prefillEnv[v.name] = v.value ?? "";
      envDescriptions[v.name] = v.desc ?? "";
    }
  } else if (template?.env_vars) {
    Object.assign(prefillEnv, template.env_vars);
  }

  // If instance is provided, merge instance env_overrides
  if (instance && template) {
    Object.assign(prefillEnv, instance.env_overrides || {});
  }

  // Volumes
  const prefillVolumes: VolumeEntry[] = [];
  if (registryImage?.config?.volumes) {
    for (const v of registryImage.config.volumes) {
      prefillVolumes.push({
        name: `{instance_id}${v.path.replace(/\//g, "-")}`,
        mount: v.path,
        desc: v.desc,
      });
    }
  } else if (template?.volumes) {
    prefillVolumes.push(...template.volumes);
  }

  // Ports
  const prefillPorts: PortEntry[] = [];
  if (registryImage?.config?.ports) {
    for (const p of registryImage.config.ports) {
      prefillPorts.push({
        internal: p.internal,
        external: p.external,
        desc: p.desc,
      });
    }
  }

  // Security options
  const prefillSecurity: SecurityOpt[] = [];
  if (registryImage?.config?.security_opt) {
    for (const s of registryImage.config.security_opt) {
      prefillSecurity.push({
        value: s.compose_var,
        desc: s.desc,
        enabled: !s.optional,
      });
    }
  }

  // Custom docker options
  const prefillCustom: CustomOpt[] = [];
  if (registryImage?.config?.custom) {
    for (const c of registryImage.config.custom) {
      prefillCustom.push({ name: c.name_compose, value: c.value, desc: c.desc });
    }
  }

  // Determine shm from custom opts or template
  const shmFromCustom = prefillCustom.find((c) => c.name === "shm_size");
  const defaultShm = shmFromCustom?.value ?? template?.shm_size ?? "1g";

  // Session config prefill
  const prefillIdleTimeout = instance?.session_config?.idle_timeout ?? "30m";
  const prefillGracePeriod = instance?.session_config?.grace_period ?? "5m";

  // State
  const [name, setName] = useState(prefillName);
  const [subdomain, setSubdomain] = useState(
    instance?.subdomain ?? slugify(prefillName)
  );
  const [image, setImage] = useState(prefillImage);
  const [icon, setIcon] = useState(
    registryImage?.project_logo ?? template?.icon ?? ""
  );
  const [memoryLimit, setMemoryLimit] = useState(template?.memory_limit ?? "4g");
  const [cpuLimit, setCpuLimit] = useState(template?.cpu_limit ?? "2.0");
  const [envVars, setEnvVars] = useState(prefillEnv);
  const [gpuEnabled, setGpuEnabled] = useState(template?.gpu_enabled ?? false);
  const [gpuDevices, setGpuDevices] = useState<string[]>([]);
  const [shmSize, setShmSize] = useState(defaultShm);
  const [volumes, setVolumes] = useState<VolumeEntry[]>(prefillVolumes);
  const [ports, setPorts] = useState<PortEntry[]>(prefillPorts);
  const [securityOpts, setSecurityOpts] = useState<SecurityOpt[]>(
    prefillSecurity
  );
  const [customOpts, setCustomOpts] = useState<CustomOpt[]>(
    prefillCustom.filter((c) => c.name !== "shm_size")
  );
  const [idleTimeout, setIdleTimeout] = useState(prefillIdleTimeout);
  const [gracePeriod, setGracePeriod] = useState(prefillGracePeriod);

  const detected = detectPortAndProtocol(registryImage, template);
  const [internalPort, setInternalPort] = useState(detected.port);
  const [internalProtocol, setInternalProtocol] = useState(detected.protocol);

  const [restartPolicy, setRestartPolicy] = useState(
    template?.restart_policy ?? "no"
  );
  const [readOnlyRootfs, setReadOnlyRootfs] = useState(
    template?.read_only_rootfs ?? false
  );
  const [tmpfs, setTmpfs] = useState<string[]>(template?.tmpfs ?? []);
  const [extraHosts, setExtraHosts] = useState<Record<string, string>>(
    template?.extra_hosts ?? {}
  );
  const [ulimits, setUlimits] = useState<
    { name: string; soft: number; hard: number }[]
  >(template?.ulimits ?? []);
  const [extraPorts, setExtraPorts] = useState<ExtraPortEntry[]>(
    template?.extra_ports ?? []
  );
  const [entrypoint, setEntrypoint] = useState<string[] | null>(
    template?.entrypoint ?? null
  );
  const [command, setCommand] = useState<string[] | null>(
    template?.command ?? null
  );
  const [devices, setDevices] = useState<string[]>(template?.devices ?? []);
  const [privileged, setPrivileged] = useState(template?.privileged ?? false);
  const [extraDockerArgs, setExtraDockerArgs] = useState<
    Record<string, unknown>
  >(template?.extra_docker_args ?? {});
  const [shared, setShared] = useState(template?.shared ?? false);

  function buildTemplateData() {
    const secOpts = securityOpts.filter((s) => s.enabled).map((s) => s.value);
    const webPort = internalPort;
    const webProtocol = internalProtocol;
    return {
      name: slugify(name),
      display_name: name,
      image,
      icon: icon || undefined,
      description:
        registryImage?.description ?? template?.description ?? "",
      env_vars: envVars,
      gpu_enabled: gpuEnabled,
      gpu_count: gpuEnabled ? (gpuDevices.length || 1) : 0,
      memory_limit: memoryLimit,
      cpu_limit: cpuLimit,
      shm_size: shmSize,
      volumes: volumes.map((v) => ({ name: v.name, mount: v.mount })),
      internal_port: webPort,
      internal_protocol: webProtocol,
      category: registryImage?.category ?? template?.category ?? undefined,
      tags: [] as string[],
      session_config: {
        idle_timeout: idleTimeout,
        grace_period: gracePeriod,
        timeout_action: "stop" as const,
        never_timeout: false,
        max_session_duration: null,
      },
      security_opts: secOpts.length > 0 ? secOpts : undefined,
      custom_opts:
        customOpts.length > 0
          ? Object.fromEntries(customOpts.map((c) => [c.name, c.value]))
          : undefined,
      restart_policy: restartPolicy,
      read_only_rootfs: readOnlyRootfs,
      tmpfs,
      extra_hosts: extraHosts,
      ulimits,
      extra_ports: extraPorts,
      entrypoint,
      command,
      devices,
      privileged,
      extra_docker_args: extraDockerArgs,
      shared,
    };
  }

  return {
    name,
    setName,
    subdomain,
    setSubdomain,
    image,
    setImage,
    icon,
    setIcon,
    memoryLimit,
    setMemoryLimit,
    cpuLimit,
    setCpuLimit,
    shmSize,
    setShmSize,
    envVars,
    setEnvVars,
    envDescriptions,
    gpuEnabled,
    setGpuEnabled,
    gpuDevices,
    setGpuDevices,
    volumes,
    setVolumes,
    ports,
    setPorts,
    securityOpts,
    setSecurityOpts,
    customOpts,
    setCustomOpts,
    idleTimeout,
    setIdleTimeout,
    gracePeriod,
    setGracePeriod,
    internalPort,
    setInternalPort,
    internalProtocol,
    setInternalProtocol,
    restartPolicy,
    setRestartPolicy,
    readOnlyRootfs,
    setReadOnlyRootfs,
    tmpfs,
    setTmpfs,
    extraHosts,
    setExtraHosts,
    ulimits,
    setUlimits,
    extraPorts,
    setExtraPorts,
    entrypoint,
    setEntrypoint,
    command,
    setCommand,
    devices,
    setDevices,
    privileged,
    setPrivileged,
    extraDockerArgs,
    setExtraDockerArgs,
    shared,
    setShared,
    buildTemplateData,
  };
}
