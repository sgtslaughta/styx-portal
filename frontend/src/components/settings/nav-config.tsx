import type { ComponentType } from "react";
import {
  Activity, Terminal, ScrollText, Users, KeyRound, HardDrive, Link2, BarChart3, UserCircle,
  FolderClock, Heart, MonitorSmartphone, SlidersHorizontal, Globe, Grid3x3, Radio, Clock, ShieldCheck, Boxes,
} from "lucide-react";
import { OverviewPane, PeoplePane, SecurityPane, TimeoutsPane, StreamingPane } from "./section-panels";
import { MetricsSessions } from "@/components/system/metrics-sessions";
import { MetricsLogs } from "@/components/system/metrics-logs";
import { HealthPanel } from "@/components/system/health-panel";
import { ServicesPanel } from "@/components/system/services-panel";
import { WorkstationsPanel } from "@/components/system/workstations-panel";
import { OAuthProvidersPanel } from "@/components/system/oauth-providers-panel";
import { ImageManager } from "@/components/system/image-manager";
import { ConnectedAccounts } from "@/components/system/connected-accounts";
import { MyProfiles } from "@/components/settings/my-profiles";
import { MatrixCard } from "@/components/settings/matrix-card";

export type SettingsSection = {
  id: string;
  label: string;
  icon: ComponentType<{ className?: string }>;
  description: string;
  tooltip: string;
  /** Extra words the "Find a setting" filter matches besides the label. */
  keywords?: string[];
  /** Return false to hide the item (e.g. Relay cost without Cloudflare credentials). */
  visible?: () => boolean;
  Component: ComponentType;
};

export type SettingsCategory = {
  id: string;
  label: string;
  icon: ComponentType<{ className?: string }>;
  adminOnly: boolean;
  sections: SettingsSection[];
};

export const CATEGORIES: SettingsCategory[] = [
  {
    id: "monitoring", label: "Monitoring", icon: BarChart3, adminOnly: true,
    sections: [
      { id: "overview", label: "Overview", icon: Activity,
        description: "Live system and instance health at a glance.",
        tooltip: "Aggregate CPU/RAM, instance counts, host info",
        keywords: ["cpu", "memory", "disk", "gpu", "resources"], Component: OverviewPane },
      { id: "health", label: "Health", icon: Heart,
        description: "Real-time diagnostic checks and 1-hour history.",
        tooltip: "Docker, database, routing, disk, and GPU diagnostics",
        keywords: ["diagnostics", "docker", "database"], Component: HealthPanel },
      { id: "sessions", label: "Sessions", icon: Terminal,
        description: "Running instances and their lifecycle actions.",
        tooltip: "View and control active instances", keywords: ["instances"], Component: MetricsSessions },
      { id: "logs", label: "Logs", icon: ScrollText,
        description: "Recent system and session events.",
        tooltip: "System event log", keywords: ["events"], Component: MetricsLogs },
    ],
  },
  {
    id: "people", label: "People", icon: Users, adminOnly: true,
    sections: [
      { id: "users", label: "Users and groups", icon: Users,
        description: "Manage accounts, roles, invitations and groups.",
        tooltip: "Create or disable users; generate invites; manage groups",
        keywords: ["invite", "role", "lock", "unlock", "members"], Component: PeoplePane },
      { id: "sso", label: "Sign-in providers", icon: KeyRound,
        description: "Configure OIDC / OAuth identity providers.",
        tooltip: "Add and manage single sign-on providers", keywords: ["sso", "oidc", "oauth"], Component: OAuthProvidersPanel },
    ],
  },
  {
    id: "infrastructure", label: "Infrastructure", icon: Boxes, adminOnly: true,
    sections: [
      { id: "workstations", label: "Workstations", icon: MonitorSmartphone,
        description: "Enroll and manage physical Linux machines.",
        tooltip: "Stream physical workstations via the Styx agent", keywords: ["agent", "enroll"], Component: WorkstationsPanel },
      { id: "services", label: "Apps", icon: Globe,
        description: "Proxy internal apps (Jellyfin, *arr, Nextcloud) through this host.",
        tooltip: "Add and configure proxied apps", keywords: ["proxy", "services", "jellyfin"], Component: ServicesPanel },
      { id: "images", label: "Images and setups", icon: HardDrive,
        description: "Pulled Docker images and cleanup.",
        tooltip: "List and remove cached images", keywords: ["docker", "templates"], Component: ImageManager },
      { id: "streaming", label: "Streaming", icon: Radio,
        description: "Relay and WebRTC settings for remote viewers.",
        tooltip: "WebRTC / TURN relay", keywords: ["turn", "webrtc", "relay", "cloudflare"], Component: StreamingPane },
    ],
  },
  {
    id: "settings", label: "Settings", icon: SlidersHorizontal, adminOnly: true,
    sections: [
      { id: "security", label: "Security and limits", icon: ShieldCheck,
        description: "Brute-force protection, rate limits, password policy and quotas.",
        tooltip: "Server behavioral settings (applied live)",
        keywords: ["rate", "lockout", "ban", "password", "quota", "brute"], Component: SecurityPane },
      { id: "timeouts", label: "Sessions and timeouts", icon: Clock,
        description: "Token lifetimes, idle timeouts and workstation features.",
        tooltip: "Session and timeout settings (applied live)",
        keywords: ["token", "idle", "timeout", "expiry", "jwt"], Component: TimeoutsPane },
    ],
  },
  {
    id: "account", label: "My account", icon: UserCircle, adminOnly: false,
    sections: [
      { id: "signin-card", label: "Sign-in card", icon: Grid3x3,
        description: "A printable code card required at password sign-in.",
        tooltip: "Generate, replace, or remove your sign-in card", keywords: ["2fa", "matrix", "password"], Component: MatrixCard },
      { id: "connected", label: "Connected accounts", icon: Link2,
        description: "Link external sign-in providers to your account.",
        tooltip: "Link or unlink Google, GitHub, and other providers", keywords: ["google", "github", "link"], Component: ConnectedAccounts },
      { id: "profiles", label: "My profiles", icon: FolderClock,
        description: "Persistent profiles saved for your instances.",
        tooltip: "Reset a saved profile", Component: MyProfiles },
    ],
  },
];

export function visibleCategories(isAdmin: boolean): SettingsCategory[] {
  return CATEGORIES.filter((c) => isAdmin || !c.adminOnly)
    .map((c) => ({ ...c, sections: c.sections.filter((s) => s.visible?.() ?? true) }))
    .filter((c) => c.sections.length > 0);
}

/** Case-insensitive filter over section labels and keywords; drops empty groups. */
export function filterCategories(cats: SettingsCategory[], q: string): SettingsCategory[] {
  const n = q.trim().toLowerCase();
  if (!n) return cats;
  const hit = (s: SettingsSection) =>
    [s.label, ...(s.keywords ?? [])].some((w) => w.toLowerCase().includes(n));
  return cats.map((c) => ({ ...c, sections: c.sections.filter(hit) })).filter((c) => c.sections.length > 0);
}
