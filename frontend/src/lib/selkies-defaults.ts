export interface SelkiesVar {
  name: string;
  value: string;
  desc: string;
  group: string;
  type: "bool" | "string" | "select" | "range";
  options?: string[];
  locked?: boolean;
}

export const SELKIES_GROUPS = ["Core", "GPU", "Display", "Audio", "Security", "UI", "Advanced"] as const;

export const SELKIES_DEFAULTS: SelkiesVar[] = [
  // Core
  { name: "PIXELFLUX_WAYLAND", value: "true", desc: "Initialize in Wayland mode (Smithay + Labwc, zero copy GPU encoding)", group: "Core", type: "bool" },
  { name: "SELKIES_DESKTOP", value: "true", desc: "Show simple panel in Wayland mode with labwc", group: "Core", type: "bool" },
  { name: "CUSTOM_PORT", value: "3000", desc: "Internal HTTP port", group: "Core", type: "string" },
  { name: "CUSTOM_HTTPS_PORT", value: "3001", desc: "Internal HTTPS port", group: "Core", type: "string" },
  { name: "CUSTOM_WS_PORT", value: "8082", desc: "Internal WebSocket port", group: "Core", type: "string" },
  { name: "CUSTOM_USER", value: "abc", desc: "HTTP Basic auth username", group: "Core", type: "string" },
  { name: "PASSWORD", value: "", desc: "HTTP Basic auth password (empty = no auth)", group: "Core", type: "string" },
  { name: "TITLE", value: "Selkies", desc: "Browser page title", group: "Core", type: "string" },
  { name: "SUBFOLDER", value: "", desc: "Subfolder path for reverse proxy (e.g. /subfolder/)", group: "Core", type: "string" },

  // GPU
  { name: "AUTO_GPU", value: "true", desc: "Auto-detect first GPU for encoding and rendering", group: "GPU", type: "bool" },
  { name: "DRI_NODE", value: "/dev/dri/renderD128", desc: "Encoding GPU (VAAPI/NVENC)", group: "GPU", type: "string" },
  { name: "DRINODE", value: "/dev/dri/renderD128", desc: "Rendering GPU (EGL/3D)", group: "GPU", type: "string" },
  { name: "DISABLE_ZINK", value: "false", desc: "Disable Zink GPU env vars (force CPU rendering)", group: "GPU", type: "bool" },
  { name: "DISABLE_DRI3", value: "false", desc: "Disable DRI3 acceleration (force CPU rendering)", group: "GPU", type: "bool" },
  { name: "SELKIES_USE_CPU", value: "false", desc: "Force CPU-based encoding", group: "GPU", type: "bool" },

  // Display
  { name: "SELKIES_FRAMERATE", value: "8-120", desc: "Framerate range (or fixed value)", group: "Display", type: "string" },
  { name: "SELKIES_ENCODER", value: "x264enc,x264enc-striped,jpeg", desc: "Video encoders (comma-separated)", group: "Display", type: "string" },
  { name: "MAX_RES", value: "15360x8640", desc: "Maximum resolution", group: "Display", type: "string" },
  { name: "NO_DECOR", value: "false", desc: "No window borders (PWA mode)", group: "Display", type: "bool" },
  { name: "NO_FULL", value: "false", desc: "Don't auto-fullscreen apps", group: "Display", type: "bool" },
  { name: "SELKIES_SECOND_SCREEN", value: "true", desc: "Enable second monitor support", group: "Display", type: "bool" },
  { name: "SELKIES_H264_CRF", value: "5-50", desc: "H.264 CRF quality range", group: "Display", type: "string" },
  { name: "SELKIES_JPEG_QUALITY", value: "1-100", desc: "JPEG quality range", group: "Display", type: "string" },
  { name: "DASHBOARD", value: "selkies-dashboard", desc: "Dashboard theme", group: "Display", type: "select", options: ["selkies-dashboard", "selkies-dashboard-zinc", "selkies-dashboard-wish"] },
  { name: "LC_ALL", value: "", desc: "Language/locale (e.g. fr_FR.UTF-8)", group: "Display", type: "string" },

  // Audio
  { name: "SELKIES_AUDIO_ENABLED", value: "true", desc: "Server-to-client audio streaming", group: "Audio", type: "bool" },
  { name: "SELKIES_MICROPHONE_ENABLED", value: "true", desc: "Client-to-server microphone", group: "Audio", type: "bool" },
  { name: "SELKIES_AUDIO_BITRATE", value: "320000", desc: "Audio bitrate", group: "Audio", type: "string" },

  // Security/Hardening
  { name: "HARDEN_DESKTOP", value: "false", desc: "Enable all desktop hardening (disables tools, sudo, terminals)", group: "Security", type: "bool" },
  { name: "HARDEN_OPENBOX", value: "false", desc: "Harden window manager (no close button, restricted keys)", group: "Security", type: "bool" },
  { name: "DISABLE_SUDO", value: "false", desc: "Remove sudo permissions", group: "Security", type: "bool" },
  { name: "DISABLE_TERMINALS", value: "false", desc: "Disable terminal emulators", group: "Security", type: "bool" },
  { name: "RESTART_APP", value: "false", desc: "Auto-restart main app if closed", group: "Security", type: "bool" },

  // UI
  { name: "SELKIES_UI_SHOW_SIDEBAR", value: "true", desc: "Show main sidebar", group: "UI", type: "bool" },
  { name: "SELKIES_CLIPBOARD_ENABLED", value: "true", desc: "Clipboard sync", group: "UI", type: "bool" },
  { name: "SELKIES_GAMEPAD_ENABLED", value: "true", desc: "Gamepad support", group: "UI", type: "bool" },
  { name: "SELKIES_FILE_TRANSFERS", value: "upload,download", desc: "File transfer directions", group: "UI", type: "string" },
  { name: "SELKIES_COMMAND_ENABLED", value: "true", desc: "Command websocket messages", group: "UI", type: "bool" },
  { name: "FILE_MANAGER_PATH", value: "", desc: "Upload/download file path", group: "UI", type: "string" },
  { name: "NO_GAMEPAD", value: "false", desc: "Disable gamepad interposer", group: "UI", type: "bool" },

  // Advanced
  { name: "START_DOCKER", value: "true", desc: "Auto-start DinD Docker (privileged containers)", group: "Advanced", type: "bool" },
  { name: "DISABLE_IPV6", value: "false", desc: "Disable IPv6", group: "Advanced", type: "bool" },
  { name: "SELKIES_DEBUG", value: "false", desc: "Debug logging", group: "Advanced", type: "bool" },
  { name: "SELKIES_ENABLE_SHARING", value: "true", desc: "Master sharing toggle", group: "Advanced", type: "bool" },
  { name: "WATERMARK_PNG", value: "", desc: "Path to watermark PNG inside container", group: "Advanced", type: "string" },
  { name: "WATERMARK_LOCATION", value: "", desc: "Watermark position (1=TL, 2=TR, 3=BL, 4=BR, 5=Center, 6=Animated)", group: "Advanced", type: "select", options: ["", "1", "2", "3", "4", "5", "6"] },
];
